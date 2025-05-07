from helpers.custom_logger import CustomLogger

import websockets
import asyncio
import json
import serial_asyncio

from services.database import Database

class Device:
    def __init__(self, writer, websocket):
        # writer: serial_asyncio.StreamWriter
        self.writer = writer
        self.alarm_last_state = 1
        self.alarm_timer = None
        self.fan_timer = None
        self.light_timer = None
        self.fan_last_state = 1
        self.light_last_state = 1
        self.websocket = websocket

    async def alarm_service(self, distance, uid,isDist=True):
        """Triggers the alarm and starts a timer to turn it off."""
        if(self.alarm_last_state == 1):

            # Turn on the alarm
            self.writer.write(f"!alarm:1#".encode())

            Database()._instance.write_action_history(
                uid=uid,
                service_type='alarm',
                value=1,
                session=None

            )

            self.alarm_last_state = 0  # Update alarm state
            
            asyncio.create_task(self._turn_off_alarm(uid))
            if isDist:
                await self._send_notification_to_server("dist_service",f"Proximity Alert: Object ahead is within {distance} cm ahead!")
            else:
                await self._send_notification_to_server("drowsiness_service",f"Fatigue Warning: Signs of drowsiness detected!")

    async def _turn_off_alarm(self, uid, delay=5):
        """Turn off the alarm after a delay (default: 5 seconds)."""
        try:
            await asyncio.sleep(delay)
            self.writer.write(f"!alarm:0#".encode())
            CustomLogger()._get_logger().info("Turn off alarm")

            self.alarm_last_state = 1  # Update alarm state

            Database()._instance.write_action_history(
                uid=uid,
                service_type='alarm',
                value=0,
                session=None

            )
            CustomLogger()._get_logger().info("Alarm turned off automatically.")
        except Exception as e:
            CustomLogger()._get_logger().exception(f"Failed to turn off alarm: {e}")

    async def fan_services(self, uid, isTemp):
        """Control the fan based on the value."""
        if(self.fan_last_state == 1):

            self.writer.write(f"!fan:50#".encode())
            CustomLogger()._get_logger().info("Turn on Fan")

            Database()._instance.write_action_history(
                uid=uid,
                service_type='fan',
                value=50,
                session=None
            )

            self.fan_last_state = 0  # Update alarm state
            CustomLogger()._get_logger().info("Turn on delay FAN")


            asyncio.create_task(self.turn_off_delay("fan"))
            if(isTemp):
                await self._send_notification_to_server("air_cond_service","Decrease AC's temperature")
            else:
                await self._send_notification_to_server("air_cond_service","Decrease AC's humidity")


    async def light_service(self, uid):
        """Control the light based on the value."""
        if(self.light_last_state == 1):

            self.writer.write(f"!headlight:2#".encode())

            Database()._instance.write_action_history(
                uid=uid,
                service_type='headlight',
                value=2,
                session=None
            )


            self.light_last_state = 0  # Update alarm state
            CustomLogger()._get_logger().info("Turn on delay Light")

            asyncio.create_task(self.turn_off_delay("headlight"))
            await self._send_notification_to_server("headlight_service","Turn on headlight")
    
    async def turn_off_delay(self, device_type, delay=5):
        """Turn off the specified device after a delay."""
        await  asyncio.sleep(delay)

        if device_type == "fan":
            # await asyncio.sleep(delay)
            CustomLogger()._get_logger().info("Turn off delay Fan")

            self.fan_last_state = 1
        elif device_type == "headlight":
            CustomLogger()._get_logger().info("Turn off delay Light")

            # await asyncio.sleep(delay)
            self.light_last_state = 1
    
    async def _send_notification_to_server(self, service_type: str, notification: str):
        websocket = self.websocket
        if not websocket:
            CustomLogger()._get_logger().warning("Cannot send notification: WebSocket connection not established")
            return
        
        try:
            await websocket.send(json.dumps(
                {
                    self.FIELD_DEVICE_ID: self.uid,
                    self.FIELD_SERVICE_TYPE: service_type,
                    self.FIELD_NOTIFICATION: notification
                }
            ))
            CustomLogger()._get_logger().info(f"Sent notification to server: {notification}")

        except websockets.exceptions.ConnectionClosed:
            CustomLogger()._get_logger().warning("Cannot send notification: WebSocket connection closed")

        except Exception as e:
            CustomLogger()._get_logger().error(f"Failed to send notification: {e}")



