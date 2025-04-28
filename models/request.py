from pydantic import BaseModel, Field
from typing import Optional, Union

class UserIdRequest(BaseModel):
    user_id: str = Field(...)

class ConnectionDetailRequest(BaseModel):
    ip_address: str = Field(...)
    port: int = Field(...)
    user_id: str = Field(...)

class ControlServiceRequest(BaseModel):
    user_id: str = Field(...)
    service_type: str = Field(...)  # e.g., "air_cond", "headlight", "drowsiness", etc.
    value: Optional[Union[str,int,float]] = None  # for service-specific values like temperature, brightness, etc.
