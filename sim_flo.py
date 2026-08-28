"""Simulated FLO Home X6 — replays the real captured OCPP flow and handles remote commands.
Used to test the bridge with no hardware."""
import asyncio
import logging

import websockets
from ocpp.v16 import ChargePoint as CP, call, call_result
from ocpp.v16.enums import ChargePointStatus, ChargePointErrorCode, Action, RemoteStartStopStatus
from ocpp.routing import on

log = logging.getLogger("sim-flo")
NOERR = ChargePointErrorCode.no_error


class SimCharger(CP):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.remote_started = False
        self.remote_stopped = False
        self.trigger_requested = None

    @on(Action.remote_start_transaction)
    async def on_remote_start(self, id_tag, **kw):
        log.info(f"<< RemoteStartTransaction id_tag={id_tag}")
        self.remote_started = True
        return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.accepted)

    @on(Action.remote_stop_transaction)
    async def on_remote_stop(self, transaction_id, **kw):
        log.info(f"<< RemoteStopTransaction tx={transaction_id}")
        self.remote_stopped = True
        return call_result.RemoteStopTransaction(status=RemoteStartStopStatus.accepted)

    @on(Action.trigger_message)
    async def on_trigger(self, requested_message, **kw):
        self.trigger_requested = requested_message
        return call_result.TriggerMessage(status="Accepted")

    @on(Action.get_configuration)
    async def on_get_config(self, key=None, **kw):
        return call_result.GetConfiguration(configuration_key=[
            {"key": "WebSocketPingInterval", "readonly": False, "value": "300"},
            {"key": "HeartbeatInterval", "readonly": False, "value": "30"}], unknown_key=[])

    @on(Action.change_configuration)
    async def on_change_config(self, key, value, **kw):
        self.last_change = (key, value)
        return call_result.ChangeConfiguration(status="Accepted")

    async def _st(self, status, connector=1):
        await self.call(call.StatusNotification(connector_id=connector, error_code=NOERR, status=status))

    async def boot(self):
        await self.call(call.BootNotification(
            charge_point_vendor="flo", charge_point_model="FLO Home X6",
            charge_point_serial_number="H5301CJ", firmware_version="3.1.7"))
        await self._st(ChargePointStatus.available, connector=0)
        await self._st(ChargePointStatus.available, connector=1)

    async def charge_session(self, meter_start=1187624):
        await self._st(ChargePointStatus.preparing)
        await self._st(ChargePointStatus.suspended_evse)
        await self.call(call.StartTransaction(connector_id=1, id_tag="00000000000000000000",
                                              meter_start=meter_start, timestamp="2026-08-27T17:28:27Z"))
        await self._st(ChargePointStatus.charging)
        # a couple of MeterValues like the real ones
        for wh, amps in [(meter_start + 40, 27.7), (meter_start + 95, 27.8)]:
            await self.call(call.MeterValues(connector_id=1, transaction_id=1, meter_value=[{
                "timestamp": "2026-08-27T17:29:00Z",
                "sampled_value": [
                    {"value": f"{wh}", "measurand": "Energy.Active.Import.Register", "unit": "Wh"},
                    {"value": f"{amps}", "measurand": "Current.Import", "unit": "A"},
                    {"value": "48.0", "measurand": "Current.Offered", "unit": "A"},
                    {"value": "235.2", "measurand": "Voltage", "unit": "V"},
                ]}]))
        return meter_start + 95

    async def end_session(self, meter_stop):
        await self._st(ChargePointStatus.finishing)
        await self._st(ChargePointStatus.available)
        await self.call(call.StopTransaction(meter_stop=meter_stop, transaction_id=1,
                                             timestamp="2026-08-27T17:29:46Z", reason="EVDisconnected"))
