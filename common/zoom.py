import logging
from urllib.parse import quote
from typing import Optional, Dict, Any
from base64 import b64encode, urlsafe_b64decode
import json
import time

from common.config import ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET

import anyio
from anyio import Semaphore
import httpx
from asynciolimiter import StrictLimiter

logger = logging.getLogger("zoom")

def decode_jwt(token):
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        
        payload = parts[1]
        payload += '=' * (4 - len(payload) %4 )
        decoded_bytes = urlsafe_b64decode(payload)
        return json.loads(decoded_bytes.decode('utf-8'))
    
    except Exception as e:
        logger.error(f"Failed to decode JWT")
        return {}

class ZoomWorkspace:

    api_url = "https://api.zoom.us/v2/"
    auth_url = "https://zoom.us/oauth/token"
    _rate_limiter = StrictLimiter(10/1)
    _access_token: Optional[str] = None
    _token_expires_at: Optional[int] = None

    @classmethod
    def is_token_expired(cls) -> bool:
        if not cls._access_token or not cls._token_expires_at:
            return True
        buffer_seconds = 300
        return time.time() + buffer_seconds >= cls._token_expires_at

    @classmethod
    async def _get_access_token(cls):
        auth_header = b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f'{cls.auth_url}?grant_type=account_credentials&account_id={ZOOM_ACCOUNT_ID}',
                    headers={
                        'Authorization': f'Basic {auth_header}',
                        'Content-Type': 'application/x-www-form-urlencoded'
                    }
                )
                
                if response.status_code != 200:
                    logger.critical(f"Failed to get access token from Zoom: {response.status_code} - {response.text}")
                    return None
                
                data = response.json()
                access_token = data.get('access_token')
                if not access_token:
                    logger.error("Access token not found in response from Zoom.")
                    return None
                
                payload = decode_jwt(access_token)
                cls._token_expires_at = payload.get('exp')
                cls._access_token = access_token
                logger.info("Successfully obtained Zoom access token")
                return access_token
                
            except httpx.RequestError as e:
                logger.exception(f"Request to Zoom API failed: {e}")
                return None
            
    @classmethod
    async def call(cls, method: str, http_method: str = "GET", **kwargs):

        await cls._rate_limiter.wait()

        if cls.is_token_expired():
            await cls._get_access_token()
        access_token = cls._access_token

        encoded_method = quote(method, safe='/')
        url = f"{cls.api_url}{encoded_method}"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        logger.info(f"Making {http_method} API call to {url}.")
        async with httpx.AsyncClient() as client:
            try:
                if http_method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=kwargs)
                elif http_method.upper() == "POST":
                    response = await client.post(url, headers=headers, json=kwargs)
                elif http_method.upper() == "PUT":
                    response = await client.put(url, headers=headers, json=kwargs)
                elif http_method.upper() == "DELETE":
                    response = await client.delete(url, headers=headers, params=kwargs)
                elif http_method.upper() == "PATCH":
                    response = await client.patch(url, headers=headers, json=kwargs)
                else:
                    logger.error(f"Unsupported HTTP method: {http_method}")
                    return None
                
                if response.status_code in [200, 201, 204]:
                    if response.status_code == 204:  # No content
                        logger.info(f"API call to {url} succeeded (no content)")
                        return {}
                    
                    response_data = response.json()
                    logger.info(f"API call to {url} succeeded")
                    return response_data
                else:
                    logger.error(f"API call to {url} failed with status code {response.status_code} and response: {response.text}")
                    return None

            except httpx.RequestError as e:
                logger.exception(f"An error occurred while making API call to {url}: {e}")
                return None

    @classmethod
    async def get(cls, method: str, **kwargs) -> Optional[Dict[str, Any]]:
        return await cls.call(method, "GET", **kwargs)

    @classmethod
    async def post(cls, method: str, **kwargs) -> Optional[Dict[str, Any]]:
        return await cls.call(method, "POST", **kwargs)

    @classmethod
    async def put(cls, method: str, **kwargs) -> Optional[Dict[str, Any]]:
        return await cls.call(method, "PUT", **kwargs)

    @classmethod
    async def delete(cls, method: str, **kwargs) -> Optional[Dict[str, Any]]:
        return await cls.call(method, "DELETE", **kwargs)

    @classmethod
    async def patch(cls, method: str, **kwargs) -> Optional[Dict[str, Any]]:
        return await cls.call(method, "PATCH", **kwargs)