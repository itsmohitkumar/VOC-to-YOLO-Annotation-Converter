```python
# db_utils.py

from sqlalchemy import text
from src.db import execute_query

def insert_campaign_image(
    username: str,
    campaign_name: str,
    post_id: str,
    image_base64: str,
    image_s3_key: str = None,
    prompt_used: str | None = None,
    generation_model: str | None = None
) -> bool:
    normalized_pid = post_id.strip().lower().replace(" ", "_")
    query = text("""
        INSERT INTO dbo.agentic_campaign_images (
            username, campaign_name, post_id,
            image_base64, image_s3_key, prompt_used, generation_model
        )
        VALUES (
            :username, :campaign_name, :post_id,
            :image_base64, :image_s3_key, :prompt_used, :generation_model
        )
    """)
    params = {
        "username": username,
        "campaign_name": campaign_name,
        "post_id": normalized_pid,
        "image_base64": image_base64,
        "image_s3_key": image_s3_key,
        "prompt_used": prompt_used,
        "generation_model": generation_model
    }
    execute_query(query, params=params, commit=True)
    return True

def list_campaign_images(
    username: str,
    campaign_name: str,
    post_id: str | None = None
) -> list[dict]:
    base_query = """
        SELECT id, post_id, image_base64, image_s3_key, prompt_used, generation_model, created_at
        FROM dbo.agentic_campaign_images
        WHERE TRIM(LOWER(username)) = TRIM(LOWER(:username))
          AND TRIM(LOWER(campaign_name)) = TRIM(LOWER(:campaign_name))
    """
    if post_id:
        normalized_pid = post_id.strip().lower().replace(" ", "_")
        base_query += " AND TRIM(LOWER(post_id)) = TRIM(LOWER(:post_id))"
        params = {"username": username, "campaign_name": campaign_name, "post_id": normalized_pid}
    else:
        params = {"username": username, "campaign_name": campaign_name}

    base_query += " ORDER BY created_at DESC"
    query = text(base_query)
    rows = execute_query(query, params=params, fetch_all=True) or []
    return [
        {
            "post_id": row[1],
            "image_base64": row[2],
        }
        for row in rows
    ]
```

```python
# api.py

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
import base64
from .db_utils import insert_campaign_image, list_campaign_images
from .response_db import fetch_campaign_responses  # existing
import json
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/{username}/{campaign_name}/upload-image/{post_id}")
async def upload_post_image(
    username: str,
    campaign_name: str,
    post_id: str,
    file: UploadFile = File(...),
    prompt_used: str | None = Form(None),
    generation_model: str | None = Form(None)
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(400, "Only image files are allowed.")
    data = await file.read()
    normal_b64 = base64.b64encode(data).decode()
    data_url = f"data:{file.content_type};base64,{normal_b64}"

    try:
        insert_campaign_image(
            username=username,
            campaign_name=campaign_name,
            post_id=post_id,
            image_base64=data_url,
            image_s3_key=None,
            prompt_used=prompt_used,
            generation_model=generation_model
        )
    except Exception as e:
        logger.error(f"Error saving image: {e}")
        raise HTTPException(500, "Failed to store image metadata.")

    return {
        "success": True,
        "message": "Image uploaded and stored successfully",
        "post_id": post_id,
        "image_base64": data_url
    }

@router.get("/{username}/{campaign_name}/responses", response_model=dict)
async def get_campaign_responses(username: str, campaign_name: str):
    responses = fetch_campaign_responses(username, campaign_name)
    if not responses:
        raise HTTPException(404, "Campaign not found.")

    json_fields = [
        "plan_response", "approve_response", "feedback_response",
        "approved_plan_v1", "approved_plan_v2", "approved_plan_v3"
    ]
    for key in json_fields:
        if key in responses and isinstance(responses[key], str):
            try:
                responses[key] = json.loads(responses[key])
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in {key}")
                raise HTTPException(500, f"Invalid JSON in {key}")

    images = list_campaign_images(username, campaign_name)
    images_by_post = {}
    for img in images:
        pid = img["post_id"]
        images_by_post.setdefault(pid, []).append(img["image_base64"])
    logger.debug(f"Images map: {images_by_post}")

    def inject(plan_obj: dict):
        cp = plan_obj.get("campaign_plan", {})
        for platform, weeks in cp.items():
            for wk, days in weeks.items():
                for dy, post in days.items():
                    key = f"{platform}_{wk}_{dy}".lower()
                    post["images"] = images_by_post.get(key, [])

    for key in json_fields:
        val = responses.get(key)
        if isinstance(val, dict) and "campaign_plan" in val:
            inject(val)

    return responses
```
