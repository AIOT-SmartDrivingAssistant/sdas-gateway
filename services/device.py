from helpers.custom_logger import CustomLogger

import asyncio
import serial_asyncio

from services.database import Database

class Device:
    def __init__(self, writer):
        # writer: serial_asyncio.StreamWriter
        self.writer = writer
        self.alarm_last_state = 0
        self.alarm_timer = None
        self.fan_timer = None
        self.light_timer = None
        self.fan_last_state = 0
        self.light_last_state = 0

    async def alarm_service(self, uid):
        """Triggers the alarm and starts a timer to turn it off."""
        if(self.alarm_last_state == 0):

            # Turn on the alarm
            await self.writer.write(f"!alarm:1#".encode())

            await Database()._instance.write_action_history(
                uid=uid,
                service_type='alarm',
                value=1
            )

            if self.alarm_timer:
                self.alarm_timer.cancel()  # Cancel any existing timer

            self.alarm_timer = asyncio.create_task(self._turn_off_alarm(uid))

    async def _turn_off_alarm(self, uid, delay=5):
        """Turn off the alarm after a delay (default: 5 seconds)."""
        try:
            await asyncio.sleep(delay)
            await self.writer.write(f"!alarm:0#".encode())
            self.alarm_last_state = 0  # Update alarm state

            await Database()._instance.write_action_history(
                uid=uid,
                service_type='alarm',
                value=0
            )
            CustomLogger()._get_logger().info("Alarm turned off automatically.")
        except Exception as e:
            CustomLogger()._get_logger().exception(f"Failed to turn off alarm: {e}")

    async def fan_services(self, uid):
        """Control the fan based on the value."""
        if(self.fan_last_state == 0):

            await self.writer.write(f"!fan:50#".encode())

            await Database()._instance.write_action_history(
                uid=uid,
                service_type='fan',
                value=50
            )

            if self.fan_timer:
                self.fan_timer.cancel()  # Cancel any existing timer

            self.fan_timer = asyncio.create_task(self.turn_off_delay("fan"))

    async def light_service(self, uid):
        """Control the light based on the value."""
        if(self.light_last_state == 0):

            await self.writer.write(f"!headlight:2#".encode())

            await Database()._instance.write_action_history(
                uid=uid,
                service_type='headlight',
                value=2
            )

            if self.light_timer:
                self.light_timer.cancel()  # Cancel any existing timer

            self.light_timer = asyncio.create_task(self.turn_off_delay("headlight"))
    
    async def turn_off_delay(self, device_type, delay=5):
        """Turn off the specified device after a delay."""
        await asyncio.sleep(delay)

        if device_type == "fan":
            # await asyncio.sleep(delay)
            self.fan_last_state = 0
        elif device_type == "headlight":
            # await asyncio.sleep(delay)
            self.light_last_state = 0



