import json
import logging
import os
import uvicorn
from app.main import create_app

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({'level': record.levelname.lower(), 'component': record.name, 'message': record.getMessage()})
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
# Disable access logs: URLs and query strings can contain sensitive data.
uvicorn.run(create_app(), host='0.0.0.0', port=9080, access_log=False, proxy_headers=False, log_config=None)
