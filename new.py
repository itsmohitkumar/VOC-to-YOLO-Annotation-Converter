from fastapi import APIRouter, UploadFile, File, HTTPException
import base64
from .db_utils import update_agentic_campaign_planner_image

router = APIRouter()

@router.post("/{username}/upload-image/{campaign_name}/{post_id}")
async def upload_post_image(
    username: str,
    campaign_name: str,
    post_id: str,
    file: UploadFile = File(...)
) -> dict:
    """
    Upload an image for a specific post_id (e.g. email_week_1_Day_1),
    store its Base64 representation in the database, and return confirmation.
    """
    # Validate image type
    if not file.content_type.startswith("image/"):
        raise HTTPException(400, "Invalid file type; only images allowed.")
    data = await file.read()
    # Encode to Base64 (no data URL prefix here)
    normal_base64 = base64.b64encode(data).decode("utf-8")
    data_url_base64 = f"data:{file.content_type};base64,{normal_base64}"
    
    # Persist in DB: column images_json stores a map post_id→list of Base64 strings
    success = update_agentic_campaign_planner_image(
        username=username,
        campaign_name=campaign_name,
        post_id=post_id,
        image_base64=data_url_base64
    )
    if not success:
        raise HTTPException(500, "Failed to save image in database.")
    return {"message": "Image uploaded successfully", "post_id": post_id}


def update_agentic_campaign_planner_image(
    username: str,
    campaign_name: str,
    post_id: str,
    image_base64: str
) -> bool:
    """
    Append a Base64 image string to the `images_json` JSONB column for a given post_id.
    The images_json column has structure: { post_id: [<dataUrlBase64>, …], … }
    """
    # Use a SQL JSONB concatenation update
    query = text("""
        UPDATE agentic_campaign_planner
        SET images_json = CASE
            WHEN images_json ? :post_id THEN
                jsonb_set(
                    images_json,
                    ARRAY[:post_id],
                    (images_json->:post_id) || to_jsonb(:image_base64::text)
                )
            ELSE
                images_json || jsonb_build_object(:post_id, to_jsonb(ARRAY[:image_base64]::text[]))
        END
        WHERE LOWER(username)=LOWER(:username)
          AND LOWER(campaign_name)=LOWER(:campaign_name)
    """)
    params = {
        "username": username,
        "campaign_name": campaign_name,
        "post_id": post_id,
        "image_base64": image_base64
    }
    result = execute_query(query, params=params, commit=True)
    return result > 0


from fastapi import APIRouter, HTTPException
import json
from .db_utils import fetch_campaign_responses

router = APIRouter()

@router.get("/{username}/{campaign_name}/responses", response_model=dict)
async def get_campaign_responses(username: str, campaign_name: str):
    """
    Retrieve all campaign responses and include Base64 images per post_id.
    """
    responses = fetch_campaign_responses(username, campaign_name)
    if not responses:
        raise HTTPException(404, f"No campaign found for user '{username}' with campaign '{campaign_name}'")
    
    # Parse JSON fields
    json_fields = [
        "plan_response",
        "approve_response",
        "feedback_response",
        "approved_plan_v1", "approved_plan_v2", "approved_plan_v3",
        "human_feedback_v1", "human_feedback_v2", "human_feedback_v3"
    ]
    for key in json_fields:
        if key in responses and responses.get(key):
            try:
                responses[key] = json.loads(responses[key])
            except json.JSONDecodeError:
                raise HTTPException(500, f"Failed to parse {key} into JSON format.")
    
    # Fetch stored images JSONB column
    # This adds an "images" key mapping post_id → list of Base64 data URLs
    query = text("""
        SELECT COALESCE(images_json, '{}'::jsonb) AS images_json
        FROM agentic_campaign_planner
        WHERE LOWER(username)=LOWER(:username)
          AND LOWER(campaign_name)=LOWER(:campaign_name)
    """)
    img_result = execute_query(query, params={
        "username": username,
        "campaign_name": campaign_name
    }, fetch_one=True)
    images_map = img_result[0] if img_result else {}
    
    # Inject images into campaign_plan structures
    def inject_images(plan: dict):
        for platform, weeks in plan.items():
            for week, days in weeks.items():
                for day_key, post in days.items():
                    post_id = f"{platform}_{week}_{day_key}"
                    post["images"] = images_map.get(post_id, [])
    
    # Inject into each JSON response that contains a campaign_plan
    for resp_key in ("plan_response", "approve_response", "feedback_response",
                     "approved_plan_v1", "approved_plan_v2", "approved_plan_v3"):
        resp = responses.get(resp_key, {})
        if isinstance(resp, dict) and "campaign_plan" in resp:
            inject_images(resp["campaign_plan"])
    
    return responses

