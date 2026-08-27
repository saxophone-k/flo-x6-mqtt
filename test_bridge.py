"""In-process integration test: bridge (DRY_RUN, no broker) + simulated Flo charger.
Exercises telemetry (boot->charge->meter->stop) and control (start/stop/charge-lock)."""
import asyncio
import json
import logging
import os

os.environ["FLO_DRY_RUN"] = "true"
os.environ["FLO_LOG_LEVEL"] = "INFO"

import websockets
from config import Config
from bridge import Bridge
import sim_flo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
PASS, FAIL = "✅ PASS", "❌ FAIL"


def check(name, cond):
    print(f"  {PASS if cond else FAIL}  {name}")
    return cond


async def main():
    Config.OCPP_PORT = 9010  # avoid clashing with any live CSMS
    bridge = Bridge(Config)
    bridge.loop = asyncio.get_running_loop()
    bridge.mqtt.connect()
    server = await websockets.serve(bridge._on_connect, "127.0.0.1", 9010, subprotocols=["ocpp1.6"])
    results = []

    async with websockets.connect("ws://127.0.0.1:9010/residential/TESTID",
                                  subprotocols=["ocpp1.6"]) as ws:
        sim = sim_flo.SimCharger("residential/TESTID", ws)
        task = asyncio.ensure_future(sim.start())
        await asyncio.sleep(0.2)

        await sim.boot()
        await asyncio.sleep(0.2)
        results.append(check("status Available after boot", bridge.state.status == "Available"))
        results.append(check("connected True after boot", bridge.state.connected is True))
        results.append(check("last_seen set after boot", bridge.state.last_seen is not None))
        results.append(check("not plugged after boot", bridge.state.status not in sim_flo.__dict__ and
                             "false" == json.loads(bridge.state.as_json())["plugged"]))

        meter_stop = await sim.charge_session()
        await asyncio.sleep(0.3)
        st = json.loads(bridge.state.as_json())
        results.append(check("status Charging", st["status"] == "Charging"))
        results.append(check("plugged true", st["plugged"] == "true"))
        results.append(check("charging true", st["charging"] == "true"))
        results.append(check("current ~27.8A", abs(bridge.state.current_a - 27.8) < 0.1))
        results.append(check("current_offered 48A (display)", bridge.state.current_offered_a == 48.0))
        results.append(check("voltage 235.2V", bridge.state.voltage_v == 235.2))
        results.append(check("power = V*I derived", abs(bridge.state.power_w - 235.2 * 27.8) < 1))
        results.append(check("session energy tracks", bridge.state.session_energy_wh == 95.0))
        results.append(check("total energy = meter", bridge.state.total_energy_wh == 1187624 + 95))

        # poka-yoke: a malformed meter value must be skipped, not crash the handler
        await sim.call(sim_flo.call.MeterValues(connector_id=1, transaction_id=1, meter_value=[{
            "timestamp": "2026-08-27T18:00:00Z", "sampled_value": [
                {"value": "NOT_A_NUMBER", "measurand": "Current.Import", "unit": "A"},
                {"value": "241.0", "measurand": "Voltage", "unit": "V"}]}]))
        await asyncio.sleep(0.3)
        results.append(check("survives malformed meter value (good value still parsed)",
                             bridge.state.voltage_v == 241.0))

        # control: HA "stop" -> RemoteStopTransaction reaches charger
        bridge._handle_command("stop", "stop")
        await asyncio.sleep(0.3)
        results.append(check("RemoteStop delivered to charger", sim.remote_stopped))

        # control: HA "start" -> RemoteStartTransaction reaches charger
        bridge._handle_command("start", "start")
        await asyncio.sleep(0.3)
        results.append(check("RemoteStart delivered to charger", sim.remote_started))

        await sim.end_session(meter_stop)
        await asyncio.sleep(0.3)
        results.append(check("status Available after unplug", bridge.state.status == "Available"))
        results.append(check("session energy final 95Wh", bridge.state.session_energy_wh == 95.0))

        # control: charge lock ON -> next StartTransaction is refused (Blocked)
        bridge._handle_command("charge_lock", "true")
        await asyncio.sleep(0.1)
        results.append(check("charge_lock state true", bridge.state.charge_lock is True))
        await sim._st(sim_flo.ChargePointStatus.preparing)
        r = await sim.call(sim_flo.call.StartTransaction(
            connector_id=1, id_tag="00000000000000000000", meter_start=1187720,
            timestamp="2026-08-27T18:00:00Z"))
        results.append(check("StartTransaction BLOCKED while locked",
                             r.id_tag_info["status"] == "Blocked"))

        task.cancel()

    server.close()
    await server.wait_closed()
    print(f"\n{'='*40}\n{sum(results)}/{len(results)} checks passed")
    return all(results)


if __name__ == "__main__":
    ok = asyncio.run(main())
    raise SystemExit(0 if ok else 1)
