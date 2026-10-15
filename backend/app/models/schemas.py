from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.security import safe_template

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')
class Credentials(Strict):
    password: str = Field(min_length=12, max_length=256)
class Login(Strict):
    password: str = Field(min_length=1, max_length=256)
class PasswordChange(Credentials):
    current_password: str = Field(max_length=256)
class DownloadCreate(Strict):
    url: str = Field(min_length=8, max_length=8192)
    destination_id: str
class DestinationCreate(Strict):
    name: str = Field(min_length=1, max_length=60)
    path: str = Field(max_length=1024)
    description: str = Field(default='', max_length=250)
    icon: Literal['folder', 'image', 'box', 'star', 'video', 'film', 'music', 'headphones', 'camera', 'heart'] = 'folder'
    is_default: bool = False
class DestinationPatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=250)
    icon: Literal['folder', 'image', 'box', 'star', 'video', 'film', 'music', 'headphones', 'camera', 'heart'] | None = None
    is_default: bool | None = None
class Settings(Strict):
    concurrency: int = Field(default=2, ge=1, le=5)
    retries: int = Field(default=3, ge=0, le=20)
    timeout: int = Field(default=30, ge=5, le=300)
    rate_limit: int = Field(default=0, ge=0, le=1000000000)
    theme: Literal['dark', 'light', 'system'] = 'dark'
    retention_days: int = Field(default=90, ge=0, le=3650)
    organisation: Literal['organised', 'flat', 'custom'] = 'organised'
    filename: str = ''
    directory: list[str] = Field(default_factory=list, max_length=8)
    advanced: dict = Field(default_factory=dict)
    @field_validator('filename')
    @classmethod
    def filename_valid(cls, v):
        return safe_template(v) if v else v
    @field_validator('directory')
    @classmethod
    def directory_valid(cls, v):
        return [safe_template(x) for x in v]
    @field_validator('advanced')
    @classmethod
    def advanced_valid(cls, v):
        # Typed allowlist: never pass arbitrary nested config through to gallery-dl.
        limits = {'sleep-request': (0, 120), 'sleep': (0, 120), 'sleep-retries': (0, 300)}
        for key, value in v.items():
            if key not in limits or type(value) not in (int, float) or not limits[key][0] <= value <= limits[key][1]:
                raise ValueError('Advanced keys allowed: sleep-request, sleep, sleep-retries (bounded seconds)')
        return v
class JobView(BaseModel):
    id: str
    url: str
    website: str
    destination_id: str
    destination_name: str
    destination_path: str
    status: Literal['queued','downloading','completed','failed','cancelled','interrupted']
    created_at: str
    started_at: str | None
    completed_at: str | None
    files: int
    total_files: int | None = None
    skipped: int
    bytes: int
    speed: float | None
    current_filename: str | None
    file_bytes: int | None
    file_total: int | None
    error: str | None
    attempts: int
class DestinationView(DestinationCreate):
    id: str
    accessible: bool
    writable: bool
