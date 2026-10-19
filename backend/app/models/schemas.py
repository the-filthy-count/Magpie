import re
import json
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator, computed_field
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
    destination_id: str | None = Field(default=None, min_length=1, max_length=128)
    category: str | None = Field(default=None, min_length=1, max_length=60)

    custom_fields: dict[str, str] = Field(default_factory=dict, max_length=10)
    filename_position: Literal['start','end'] = 'start'

    @field_validator('custom_fields')
    @classmethod
    def custom_fields_valid(cls, fields):
        cleaned={}
        for key,value in fields.items():
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_ -]{0,39}',key):
                raise ValueError('Custom field names must start with a letter and use at most 40 letters, numbers, spaces, underscores or hyphens')
            value=value.strip()
            if not value or len(value)>100:
                raise ValueError('Custom field values must contain 1–100 characters')
            cleaned[key]=value
        return cleaned

    @model_validator(mode='after')
    def destination_selector(self):
        if (self.destination_id is None) == (self.category is None):
            raise ValueError('Provide exactly one of destination_id or category')
        if self.category is not None:
            self.category = self.category.strip()
            if not self.category:
                raise ValueError('Category cannot be blank')
        return self

class DestinationCreate(Strict):
    name: str = Field(min_length=1, max_length=60)
    path: str = Field(max_length=1024)
    description: str = Field(default='', max_length=250)
    icon: Literal['folder', 'image', 'box', 'star', 'video', 'film', 'music', 'headphones', 'camera', 'heart'] = 'folder'
    is_default: bool = False
    organisation: Literal['inherit','organised','flat','flat_gallery','custom'] = 'inherit'
class DestinationPatch(Strict):
    path: str | None = Field(default=None, min_length=1, max_length=1024)
    name: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=250)
    icon: Literal['folder', 'image', 'box', 'star', 'video', 'film', 'music', 'headphones', 'camera', 'heart'] | None = None
    is_default: bool | None = None
    organisation: Literal['inherit','organised','flat','flat_gallery','custom'] | None = None

class SiteRule(Strict):
    website: str = Field(min_length=1, max_length=253)
    organisation: Literal['organised','flat','flat_gallery','custom'] | None = None
    filename: str | None = None
    retries: int | None = Field(default=None, ge=0, le=20)
    timeout: int | None = Field(default=None, ge=5, le=300)
    rate_limit: int | None = Field(default=None, ge=0, le=1000000000)
    sleep_request: float | None = Field(default=None, ge=0, le=120)

    @field_validator('website')
    @classmethod
    def website_valid(cls, v):
        v=v.strip().lower()
        if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',v) or '..' in v or any(not x or x.startswith('-') or x.endswith('-') for x in v.split('.')):
            raise ValueError('Use a website hostname without a URL or path')
        return v

    @field_validator('filename')
    @classmethod
    def filename_valid(cls,v):
        return safe_template(v) if v else v

class Settings(Strict):
    concurrency: int = Field(default=2, ge=1, le=5)
    retries: int = Field(default=3, ge=0, le=20)
    timeout: int = Field(default=30, ge=5, le=300)
    rate_limit: int = Field(default=0, ge=0, le=1000000000)
    theme: Literal['dark', 'light', 'system'] = 'dark'
    retention_days: int = Field(default=90, ge=0, le=3650)
    organisation: Literal['organised', 'flat', 'flat_gallery', 'custom'] = 'organised'
    filename: str = ''
    directory: list[str] = Field(default_factory=list, max_length=8)
    advanced: dict = Field(default_factory=dict)
    video_quality: Literal['best','1080','720','480'] = 'best'
    video_format: Literal['best','mp4'] = 'best'
    playlist: Literal['all','single'] = 'all'
    media_filter: Literal['all','images','videos','extensions'] = 'all'
    extensions: list[str] = Field(default_factory=list, max_length=50)
    max_files: int = Field(default=0, ge=0, le=100000)
    max_file_size: int = Field(default=0, ge=0, le=1000000000000)
    subtitles: Literal['off','manual','automatic'] = 'off'
    subtitle_languages: list[str] = Field(default_factory=lambda:['en'], max_length=20)
    schedule_enabled: bool = False
    schedule_start: str = '00:00'
    schedule_end: str = '00:00'
    publish_when_complete: bool = True
    in_progress_path: str = Field(default='', max_length=4096)
    resume_interrupted: bool = False
    site_rules: list[SiteRule] = Field(default_factory=list, max_length=50)

    @field_validator('extensions')
    @classmethod
    def extensions_valid(cls, v):
        if any(not re.fullmatch(r'[A-Za-z0-9]{1,12}',x) for x in v):
            raise ValueError('Extensions must be letters/numbers without dots')
        return list(dict.fromkeys(x.lower() for x in v))

    @field_validator('subtitle_languages')
    @classmethod
    def languages_valid(cls,v):
        if any(not re.fullmatch(r'[A-Za-z0-9-]{1,20}',x) for x in v):
            raise ValueError('Use language codes such as en or en-US')
        return v

    @field_validator('schedule_start','schedule_end')
    @classmethod
    def time_valid(cls,v):
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',v):
            raise ValueError('Use HH:MM in 24-hour time')
        return v

    @model_validator(mode='after')
    def extras_valid(self):
        if self.media_filter=='extensions' and not self.extensions:
            raise ValueError('Select at least one extension')
        if self.subtitles!='off' and not self.subtitle_languages:
            raise ValueError('Select at least one subtitle language')
        if len({r.website for r in self.site_rules})!=len(self.site_rules):
            raise ValueError('Website defaults must have unique hostnames')
        return self
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
    custom_fields: dict[str,str] = Field(default_factory=dict)
    filename_position: Literal['start','end'] = 'start'
    phase: Literal['downloading','publishing'] = 'downloading'
    staging_path: str | None = None
    engine: Literal['gallery-dl','yt-dlp'] | None = None
    engine_extractor: str | None = None

    @field_validator('custom_fields',mode='before')
    @classmethod
    def custom_fields_json(cls,value):
        return json.loads(value) if isinstance(value,str) else value

    @computed_field(description='File completion from measured bytes, 0–100; confirmed single-file jobs stay at 100 after completion')
    @property
    def file_progress_percent(self) -> float | None:
        from app.core.progress import progress_fields
        return progress_fields(dict(file_bytes=self.file_bytes,file_total=self.file_total,files=self.files,skipped=self.skipped,total_files=self.total_files))['file_progress_percent']

    @computed_field(description='Album completion, 0–100; mirrors file progress for confirmed single-file jobs, otherwise uses handled file counts')
    @property
    def album_progress_percent(self) -> float | None:
        from app.core.progress import progress_fields
        return progress_fields(dict(file_bytes=self.file_bytes,file_total=self.file_total,files=self.files,skipped=self.skipped,total_files=self.total_files))['album_progress_percent']

class DestinationView(DestinationCreate):
    id: str
    accessible: bool
    writable: bool

class ApiTokenCreate(Strict):
    name: str = Field(min_length=1, max_length=60)
    expires_days: int | None = Field(default=90, ge=1, le=365)

class ApiTokenView(BaseModel):
    id: str
    name: str
    created_at: str
    expires_at: float | None

class ApiTokenIssued(ApiTokenView):
    token: str


class NetworkView(BaseModel):
    ip: str | None
    country: str | None
    city: str | None
    isp: str | None
    checked_at: str | None
    stale: bool
    error: str | None
