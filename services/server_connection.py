from datetime import datetime
from helpers.custom_logger import CustomLogger

import os
import websockets
import asyncio
import json

from services.iot import IOTSystem

class ServerConnection:
    _instance = None

    FIELD_UID = "uid"
    FIELD_DEVICE_ID = "device_id"
    FIELD_COMMAND = "command"
    FIELD_COMMAND_ID = "command_id"
    FIELD_TARGET = "target"
    FIELD_VALUE = "value"
    FIELD_STATUS = "status"
    FIELD_MESSAGE = "message"
    FIELD_SERVICE_TYPE = "service_type"
    FIELD_DESCRIPTION = "description"
    FIELD_TIMESTAMP = "timestamp"

    def __new__(cls, uid: str = None):
        if not cls._instance:
            cls._instance = super(ServerConnection, cls).__new__(cls)
            cls._instance._init_instance(uid)
        return cls._instance
    
    def _init_instance(self, uid: str = None):
        self.websocket = None
        self.uid = uid

        if uid is None:
            self.connection_url = None
        else:
            self.connection_url = f"{os.getenv('WEBSOCKETS_URL')}/{self.uid}"

    async def _connect_to_server(self):
        if self.uid is None:
            raise Exception("User ID is required to connect to the server.")

        max_retries = 5
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                websocket = await websockets.connect(self.connection_url)
                self.websocket = websocket
                IOTSystem()._instance.websocket = websocket
                IOTSystem()._instance.uid = self.uid
                CustomLogger()._get_logger().info(f"Connected to server as {self.uid}")

                # Run send and receive tasks concurrently
                await asyncio.gather(
                    self._handle_server_commands(websocket),
                )

            except (websockets.exceptions.WebSocketException, ConnectionError) as e:
                CustomLogger()._get_logger().error(f"Connection failed (attempt {attempt + 1}/{max_retries}): {e}")

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)

                else:
                    CustomLogger()._get_logger().error("Max retries reached. Giving up.")
                    break

            except Exception as e:
                CustomLogger()._get_logger().error(f"Unexpected error: {e}")
                break

    async def _handle_server_commands(self, websocket):
        try:
            async for message in websocket:
                data = json.loads(message)
                if "error" in data:
                    CustomLogger()._get_logger().error(f"Error from server: {data['error']}")
                    continue

                CustomLogger()._get_logger().info(f"Received command: {data}")

                if self.FIELD_COMMAND not in data or self.FIELD_COMMAND_ID not in data:
                    CustomLogger()._get_logger().error(f"Invalid message: {data}")
                    websocket.send(json.dumps(
                        {
                            self.FIELD_DEVICE_ID: "none",
                            self.FIELD_COMMAND_ID: "none",
                            self.FIELD_STATUS: "error",
                            self.FIELD_MESSAGE: "Invalid message"
                        }
                    ))
                    continue

                command = data[self.FIELD_COMMAND]
                command_id = data[self.FIELD_COMMAND_ID]

                if self.FIELD_TARGET not in command or self.FIELD_VALUE not in command:
                    CustomLogger()._get_logger().error(f"Invalid command: {data}")
                    websocket.send(json.dumps(
                        {
                            self.FIELD_DEVICE_ID: self.uid,
                            self.FIELD_COMMAND_ID: command_id,
                            self.FIELD_STATUS: "error",
                            self.FIELD_MESSAGE: "Invalid command: Missing target or value"
                        }
                    ))
                    continue

                notification_message = None

                if command[self.FIELD_TARGET] == "system":
                    if command[self.FIELD_VALUE] == "on":
                        try:
                            await IOTSystem()._start_system(self.uid)
                            services = [
                                    "air_cond_service",
                                    "headlight_service",
                                    "drowsiness_service",
                                    "distance_service"
                                ]
                            
                            for service in services:
                                await IOTSystem()._control_service(self.uid, service, "on")

                            CustomLogger()._get_logger().info(f"Started system {self.uid}")

                            await websocket.send(json.dumps(
                                {
                                    self.FIELD_DEVICE_ID: self.uid,
                                    self.FIELD_COMMAND_ID: command_id,
                                    self.FIELD_STATUS: "success"
                                }
                            ))

                            notification_message = "Turn on system successfully"
                        
                        except Exception as e:
                            CustomLogger()._get_logger().error(f"Failed to start system: {e.args[0]}")
                            
                            await websocket.send(json.dumps(
                                {
                                    self.FIELD_DEVICE_ID: self.uid,
                                    self.FIELD_COMMAND_ID: command_id,
                                    self.FIELD_STATUS: "fail",
                                    self.FIELD_MESSAGE: str(e.args[0])
                                }
                            ))
                            continue

                    elif command[self.FIELD_VALUE] == "off":
                        try:
                            await IOTSystem()._stop_system()
                            services = [
                                    "air_cond_service",
                                    "headlight_service",
                                    "drowsiness_service",
                                    "distance_service"
                                ]
                            
                            for service in services:
                                await IOTSystem()._control_service(self.uid, service, "off")

                            CustomLogger()._get_logger().info(f"Stopped system {self.uid}")

                            await websocket.send(json.dumps(
                                {
                                    self.FIELD_DEVICE_ID: self.uid,
                                    self.FIELD_COMMAND_ID: command_id,
                                    self.FIELD_STATUS: "success"
                                }
                            ))

                            notification_message = "Turn off system successfully"

                        except Exception as e:
                            CustomLogger()._get_logger().error(f"Failed to stop system: {e}")
                            await websocket.send(json.dumps(
                                {
                                    self.FIELD_DEVICE_ID: self.uid,
                                    self.FIELD_COMMAND_ID: command_id,
                                    self.FIELD_STATUS: "fail",
                                    self.FIELD_MESSAGE: str(e.args[0])
                                }
                            ))
                            continue
                        
                elif "service" in command[self.FIELD_TARGET]:
                    try:
                        await IOTSystem()._control_service(self.uid, command[self.FIELD_TARGET], command[self.FIELD_VALUE])
 
                        CustomLogger()._get_logger().info(f"Controlled service {command['target']} with value {command['value']}")

                        await websocket.send(json.dumps(
                            {
                                self.FIELD_DEVICE_ID: self.uid,
                                self.FIELD_COMMAND_ID: command_id,
                                self.FIELD_STATUS: "success"
                            }
                        ))

                        notification_message = f"Execute command on \"{command['target']}\" successfully"
                
                    except Exception as e:
                        CustomLogger()._get_logger().error(f"Failed to control service: {e.args[0]}")

                        await websocket.send(json.dumps(
                            {
                                self.FIELD_DEVICE_ID: self.uid,
                                self.FIELD_COMMAND_ID: command_id,
                                self.FIELD_STATUS: "fail",
                                self.FIELD_MESSAGE: str(e.args[0])
                            }
                        ))
                        continue

                elif "threshold" in command[self.FIELD_TARGET]:
                    try:
                        await IOTSystem().set_thresholds(command[self.FIELD_TARGET], command[self.FIELD_VALUE])
                        CustomLogger()._get_logger().info(f"Set sensor threshold {command['target']} with value {command['value']}")

                        await websocket.send(json.dumps(
                            {
                                self.FIELD_DEVICE_ID: self.uid,
                                self.FIELD_COMMAND_ID: command_id,
                                self.FIELD_STATUS: "success"
                            }
                        ))
                        notification_message = f"Execute command on \"{command['target']}\" successfully"

                    except Exception as e:
                        CustomLogger()._get_logger().error(f"Failed to set sensor threshold: {e.args[0]}")

                        await websocket.send(json.dumps(
                            {
                                self.FIELD_DEVICE_ID: self.uid,
                                self.FIELD_COMMAND_ID: command_id,
                                self.FIELD_STATUS: "fail",
                                self.FIELD_MESSAGE: str(e.args[0])
                            }
                        ))
                        continue

                await self._send_notification_to_server(
                    service_type=command[self.FIELD_TARGET],
                    description=notification_message
                )

        except websockets.exceptions.ConnectionClosed:
            CustomLogger()._get_logger().warning("Disconnected")
 
        except Exception as e:
            CustomLogger()._get_logger().error(f"Error receiving commands: {e}")

    def _disconnect_server_connection(self):
        try:
            self.websocket.close()
            CustomLogger()._get_logger().info(f"Disconnected from server: {self.uid}")

        except Exception as e:
            CustomLogger()._get_logger().error(f"Failed to disconnect from server: {e}")

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