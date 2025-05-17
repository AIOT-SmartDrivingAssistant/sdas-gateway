from datetime import datetime
from helpers.custom_logger import CustomLogger

import websockets
import asyncio
import json
# import serial_asyncio

# from services.database import Database

class Device:
    FIELD_DEVICE_ID = "device_id"
    FIELD_SERVICE_TYPE = "service_type"
    FIELD_DESCRIPTION = "description"
    FIELD_TIMESTAMP = "timestamp"

    def __init__(self, writer, uid, websocket):
        # writer: serial_asyncio.StreamWriter
        self.writer = writer


        self.alarm_last_state_dist = 1
        self.alarm_last_state_drowisness = 1 
        
        self.light_last_state = 1
        self.light_is_on = 1
        self.light_is_hight = 0

        self.fan_last_state = 1
        self.fan_is_on = 1
        self.temp_is_high = 0
        self.humid_is_high = 0
        self.last_value_temp = 0
        self.last_value_humid = 0 

        self.websocket = websocket
        self.uid = uid

    async def alarm_service(self, uid, value, threshold, isDist=True):
        """
        Triggers the alarm and starts a timer to turn it off.
        Sends notification if alarm is triggered.
        """
        dist_alarm_triggered = False
        drowsiness_alarm_triggered = False
        notification_service = "alarm_service"
        notification_msg = ""
        
        if isDist:
            if self.alarm_last_state_dist == 1 and value < threshold:
                dist_alarm_triggered = True
                self.alarm_last_state_dist = 0
                 
                notification_msg = f"Proximity Alert: Object ahead is within {value} cm ahead!"
                CustomLogger()._get_logger().info(f"Alarm Distance not activated (value={value}, threshold={threshold})")

        else:
            if self.alarm_last_state_drowisness == 1:
                
                drowsiness_alarm_triggered = True
                self.alarm_last_state_drowisness = 0

                notification_msg = "Fatigue Warning: Signs of drowsiness detected!"
                CustomLogger()._get_logger().info(f"Alarm Drowisness not activated (value={value}, threshold={threshold})")


        # Xử lý bật alarm nếu có bất kỳ trigger nào
        if dist_alarm_triggered or drowsiness_alarm_triggered:
            try:
                self.writer.write(f"!alarm:1#".encode())
                CustomLogger()._get_logger().info("Alarm triggered and turned ON.")
                asyncio.create_task(self._turn_off_alarm())
            except Exception as e:
                CustomLogger()._get_logger().exception(f"Failed to trigger alarm: {e}")

            if notification_service and notification_msg:
                await self._send_notification_to_server(notification_service, notification_msg)


    async def _turn_off_alarm(self, delay=5):
        """
        Turn off the alarm after a delay (default: 5 seconds).
        Resets alarm and light states as needed.
        """
        try:
            await asyncio.sleep(delay)
            self.writer.write(f"!alarm:0#".encode())
            CustomLogger()._get_logger().info("Alarm turned OFF after delay.")

            # Reset states
            if self.alarm_last_state_drowisness == 0:
                self.alarm_last_state_drowisness = 1
            elif self.alarm_last_state_dist == 0:
                self.alarm_last_state_dist = 1

            CustomLogger()._get_logger().info("Alarm and related states reset automatically.")
        except Exception as e:
            CustomLogger()._get_logger().exception(f"Failed to turn off alarm: {e}")

    async def fan_services(self, value, threshold, isTemp):
        """
        Cải thiện: Điều khiển quạt dựa trên giá trị nhiệt độ/độ ẩm và ngưỡng.
        - Bật quạt khi cả nhiệt độ và độ ẩm đều cao hơn ngưỡng.
        - Tắt quạt khi giá trị giảm xuống dưới ngưỡng.
        - Gửi thông báo và ghi log chi tiết.
        """
        logger = CustomLogger()._get_logger()
        max_speed = 100
        min_speed = 30

        # Cập nhật trạng thái nhiệt độ/độ ẩm
        if isTemp:
            if value > threshold:
                self.temp_is_high = 1
                self.last_value_temp = value
            else:
                self.temp_is_high = 0
        else:
            if value > threshold:
                self.humid_is_high = 1
                self.last_value_humid = value
            else:
                self.humid_is_high = 0

        # Xác định điều kiện bật quạt
        if self.temp_is_high and self.humid_is_high:
            if self.fan_last_state == 1:
                # Tính tốc độ quạt dựa trên trung bình nhiệt độ và độ ẩm vượt ngưỡng
                if isTemp:
                    percent = min((self.last_value_temp - threshold) / threshold, 1.0)
                else:
                    percent = min((self.last_value_humid - threshold) / threshold, 1.0)
                    
                speed = int(min_speed + percent * (max_speed - min_speed))

                self.writer.write(f"!fan:{speed}#".encode())
                self.fan_last_state = 0
                self.fan_is_on = 1
                asyncio.create_task(self.turn_off_delay("fan"))
                await self._send_notification_to_server(
                    "air_cond_service",
                    f"Decrease AC's temperature and humidity (fan speed {speed})"
                )
        # Điều kiện tắt quạt
        elif (not self.temp_is_high or not self.humid_is_high) and self.fan_is_on == 1:
            self.writer.write(f"!fan:0#".encode())
            self.fan_is_on = 0
            self.fan_last_state = 0
            msg = ""
            if isTemp and not self.temp_is_high:
                msg = "Increase AC's temperature, Turn off Fan"
            elif not isTemp and not self.humid_is_high:
                msg = "Increase AC's humidity, Turn off Fan"
            else:
                msg = "Turn off Fan"
            await self._send_notification_to_server("air_cond_service", msg)
            asyncio.create_task(self.turn_off_delay("fan"))

    async def light_service(self, value, threshold):
        """
        Control the light based on the value and threshold.
        """
        if value < threshold and self.light_last_state == 1:
            max_light = 4
            min_light = 1

            # Tính phần trăm thiếu sáng, giới hạn tối đa 1.0
            percent = min((threshold - value) / threshold, 1.0)
            light_level = int(min_light + percent * (max_light - min_light))

            self.writer.write(f"!light:{light_level}#".encode())
            self.light_is_on = 1
            self.light_last_state = 0

            asyncio.create_task(self.turn_off_delay("headlight"))

            await self._send_notification_to_server("headlight_service", f"Turn on headlight (level {light_level})")
        elif value > threshold and self.light_is_on == 1:

            self.writer.write(f"!light:0#".encode())

            self.light_is_on = 0

            asyncio.create_task(self.turn_off_delay("headlight"))

            await self._send_notification_to_server("headlight_service", f"Turn off headlight")

        else:
            CustomLogger()._get_logger().info(f"Light not activated (value={value}, threshold={threshold}, light_last_state={self.light_last_state})")
        
    async def turn_off_delay(self, device_type, delay=5):
        """Turn off the specified device after a delay."""
        await  asyncio.sleep(delay)

        if device_type == "fan":
            self.fan_last_state = 1

        elif device_type == "headlight":
            self.light_last_state = 1
    
    async def _send_notification_to_server(self, service_type: str, description: str):
        websocket = self.websocket
        if not websocket:
            CustomLogger()._get_logger().warning("Cannot send notification: WebSocket connection not established")
            return
        
        try:
            await websocket.send(json.dumps(
                {
                    self.FIELD_DEVICE_ID: self.uid,
                    self.FIELD_SERVICE_TYPE: service_type,
                    self.FIELD_DESCRIPTION: description,
                    self.FIELD_TIMESTAMP: datetime.now().isoformat()
                }
            ))
            CustomLogger()._get_logger().info(f"Sent notification to server: {description}")

        except websockets.exceptions.ConnectionClosed:
            CustomLogger()._get_logger().warning("Cannot send notification: WebSocket connection closed")

        except Exception as e:
            CustomLogger()._get_logger().error(f"Failed to send notification: {e}")




