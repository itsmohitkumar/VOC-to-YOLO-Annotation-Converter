# Complete Image Upload and Retrieval System
# Add this code to your existing src/api/api.py file

# ========================= ADDITIONAL IMPORTS =========================
# Add these imports to your existing imports in src/api/api.py

import base64
import mimetypes
import os
from PIL import Image
import io

# ========================= DATABASE HELPER FUNCTIONS =========================
# Add these functions to your src/api/db_utils.py file

def get_existing_campaign_images(username: str, campaign_name: str) -> List[Dict[str, Any]]:
    """Get existing campaign images from database."""
    try:
        query = text("""
            SELECT campaign_images
            FROM agentic_campaign_planner
            WHERE TRIM(LOWER(username)) = TRIM(LOWER(:username))
              AND TRIM(LOWER(campaign_name)) = TRIM(LOWER(:campaign_name))
        """)
        params = {"username": username, "campaign_name": campaign_name}
        result = execute_query(query, params=params, fetch_one=True)
        
        if result and result[0]:
            try:
                return json.loads(result[0])
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in campaign_images for {username}/{campaign_name}")
                return []
        return []
        
    except Exception as e:
        logger.error(f"Error retrieving existing campaign images: {e}")
        return []


def get_campaign_images_from_db(username: str, campaign_name: str) -> List[Dict[str, Any]]:
    """
    Retrieve campaign images from database.
    
    Args:
        username: User identifier
        campaign_name: Campaign identifier
        
    Returns:
        List of image dictionaries
    """
    try:
        query = text("""
            SELECT campaign_images
            FROM agentic_campaign_planner
            WHERE TRIM(LOWER(username)) = TRIM(LOWER(:username))
              AND TRIM(LOWER(campaign_name)) = TRIM(LOWER(:campaign_name))
        """)
        params = {"username": username, "campaign_name": campaign_name}
        result = execute_query(query, params=params, fetch_one=True)
        
        if result and result[0]:
            try:
                images = json.loads(result[0])
                logger.info(f"Retrieved {len(images)} images from database for {username}/{campaign_name}")
                return images
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in campaign_images for {username}/{campaign_name}")
                return []
        
        logger.info(f"No images found in database for {username}/{campaign_name}")
        return []
        
    except Exception as e:
        logger.error(f"Error retrieving campaign images from database: {e}")
        return []


def get_images_for_location(username: str, campaign_name: str, platform: str, week_key: str, day_key: str) -> List[Dict[str, Any]]:
    """
    Get images for a specific campaign location.
    
    Args:
        username: User identifier
        campaign_name: Campaign identifier
        platform: Social media platform
        week_key: Week identifier
        day_key: Day identifier
        
    Returns:
        List of image dictionaries for the specific location
    """
    try:
        all_images = get_campaign_images_from_db(username, campaign_name)
        location_images = [
            img for img in all_images 
            if (img.get('platform') == platform and 
                img.get('week_key') == week_key and 
                img.get('day_key') == day_key)
        ]
        return location_images
        
    except Exception as e:
        logger.error(f"Error retrieving images for location {platform}/{week_key}/{day_key}: {e}")
        return []


def delete_campaign_image(username: str, campaign_name: str, image_filename: str, platform: str, week_key: str, day_key: str) -> bool:
    """
    Delete a specific image from campaign images.
    
    Args:
        username: User identifier
        campaign_name: Campaign identifier
        image_filename: Name of the image file to delete
        platform: Social media platform
        week_key: Week identifier
        day_key: Day identifier
        
    Returns:
        True if image was deleted, False otherwise
    """
    try:
        # Get existing images
        existing_images = get_existing_campaign_images(username, campaign_name)
        
        # Filter out the image to delete
        updated_images = [
            img for img in existing_images
            if not (img.get('filename') == image_filename and
                   img.get('platform') == platform and
                   img.get('week_key') == week_key and
                   img.get('day_key') == day_key)
        ]
        
        # Check if any image was actually removed
        if len(updated_images) == len(existing_images):
            logger.warning(f"Image {image_filename} not found for deletion")
            return False
        
        # Update database with remaining images
        campaign_images_json = json.dumps(updated_images, ensure_ascii=False)
        
        update_agentic_campaign_planner(
            username=username,
            campaign_name=campaign_name,
            campaign_images=campaign_images_json
        )
        
        logger.info(f"Deleted image {image_filename} from {username}/{campaign_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting campaign image: {e}")
        return False

# ========================= IMAGE UPLOAD API ENDPOINT =========================
# Add this endpoint to your existing router in src/api/api.py

@router.post("/{username}/{campaign_name}/upload_images")
async def upload_campaign_images(
    username: str,
    campaign_name: str,
    platform: str = Form(...),
    week_key: str = Form(...),
    day_key: str = Form(...),
    files: List[UploadFile] = File(...)
):
    """
    Upload images for a specific campaign day and store them directly in the database.
    
    Args:
        username: User identifier
        campaign_name: Campaign identifier
        platform: Social media platform (instagram, facebook, x, whatsapp, email, sms)
        week_key: Week identifier (week_1, week_2, etc.)
        day_key: Day identifier (Day_1, Day_2, etc.)
        files: List of image files to upload
    """
    try:
        logger.info(f"Starting image upload for {username}/{campaign_name}/{platform}/{week_key}/{day_key}")
        
        # Validate user and campaign
        user_data = get_user_by_username(username)
        if not user_data:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
            
        user_campaigns = get_user_campaigns(username)
        campaign_exists = any(
            (campaign.get("campaign_name", "") or "").lower() == campaign_name.lower()
            for campaign in user_campaigns
        )
        if not campaign_exists:
            raise HTTPException(status_code=404, detail=f"Campaign '{campaign_name}' not found for user '{username}'")
        
        # Validate platform
        if platform not in ALLOWED_PLATFORMS:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid platform '{platform}'. Allowed: {ALLOWED_PLATFORMS}"
            )
        
        # Validate file types and sizes
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
        ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        
        if len(files) > 5:  # Limit to 5 images per upload
            raise HTTPException(status_code=400, detail="Maximum 5 images allowed per upload")
        
        uploaded_images = []
        failed_uploads = []
        
        for i, file in enumerate(files):
            try:
                # Validate file
                if not file.filename:
                    failed_uploads.append({"file": f"file_{i}", "error": "No filename provided"})
                    continue
                
                file_ext = os.path.splitext(file.filename)[1].lower()
                if file_ext not in ALLOWED_EXTENSIONS:
                    failed_uploads.append({
                        "file": file.filename, 
                        "error": f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
                    })
                    continue
                
                # Read and validate file content
                file_content = await file.read()
                if len(file_content) > MAX_FILE_SIZE:
                    failed_uploads.append({
                        "file": file.filename,
                        "error": f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
                    })
                    continue
                
                # Validate image content using PIL
                try:
                    img = Image.open(io.BytesIO(file_content))
                    img.verify()  # Verify it's a valid image
                    # Reset stream position after verify
                    img = Image.open(io.BytesIO(file_content))
                    width, height = img.size
                except Exception:
                    failed_uploads.append({
                        "file": file.filename,
                        "error": "Invalid image file"
                    })
                    continue
                
                # Convert image to base64
                base64_data = base64.b64encode(file_content).decode('utf-8')
                
                # Create image metadata
                image_metadata = {
                    "filename": file.filename,
                    "platform": platform,
                    "week_key": week_key,
                    "day_key": day_key,
                    "content_type": file.content_type or mimetypes.guess_type(file.filename)[0] or 'image/jpeg',
                    "file_size": len(file_content),
                    "width": width,
                    "height": height,
                    "base64_data": base64_data,
                    "upload_timestamp": datetime.now().isoformat()
                }
                
                uploaded_images.append(image_metadata)
                logger.info(f"Successfully processed image: {file.filename}")
                    
            except Exception as e:
                logger.error(f"Error processing file {file.filename}: {e}")
                failed_uploads.append({
                    "file": file.filename,
                    "error": f"Processing failed: {str(e)}"
                })
                continue
        
        # Store images in database if any were successfully processed
        if uploaded_images:
            try:
                # Get existing campaign images from database
                existing_images = get_existing_campaign_images(username, campaign_name)
                
                # Add new images to existing ones
                all_images = existing_images + uploaded_images
                
                # Update database with all images
                campaign_images_json = json.dumps(all_images, ensure_ascii=False)
                
                update_agentic_campaign_planner(
                    username=username,
                    campaign_name=campaign_name,
                    campaign_images=campaign_images_json
                )
                
                logger.info(f"Updated database with {len(uploaded_images)} new images")
                
            except Exception as e:
                logger.error(f"Failed to update database with images: {e}")
                raise HTTPException(status_code=500, detail="Failed to save images to database")
        
        response_message = f"Processed {len(files)} files: {len(uploaded_images)} successful, {len(failed_uploads)} failed"
        
        return {
            "success": True,
            "message": response_message,
            "uploaded_images": [
                {
                    "filename": img["filename"],
                    "platform": img["platform"],
                    "week_key": img["week_key"], 
                    "day_key": img["day_key"],
                    "size": img["file_size"],
                    "content_type": img["content_type"],
                    "dimensions": f"{img['width']}x{img['height']}"
                }
                for img in uploaded_images
            ],
            "failed_uploads": failed_uploads,
            "total_processed": len(files),
            "successful_uploads": len(uploaded_images),
            "failed_uploads_count": len(failed_uploads)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in image upload: {e}")
        raise HTTPException(status_code=500, detail="Image upload failed: Contact support team!")

# ========================= ENHANCED RESPONSES API ENDPOINT =========================
# Add this endpoint to your existing router in src/api/api.py

@router.get("/{username}/{campaign_name}/responses", response_model=dict)
async def get_campaign_responses(
    username: str,
    campaign_name: str,
    include_images: bool = True,
    image_format: str = "url"  # "url" or "base64"
):
    """
    Get campaign responses with optional image data.
    
    Args:
        username: User identifier
        campaign_name: Campaign identifier
        include_images: Whether to include image data in response
        image_format: Format for images - "url" for imagePath format or "base64" for data URLs
    """
    try:
        logger.info(f"Retrieving campaign responses for {username}/{campaign_name}")
        
        # Validate user and campaign
        user_data = get_user_by_username(username)
        if not user_data:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
            
        user_campaigns = get_user_campaigns(username)
        campaign_exists = any(
            (campaign.get("campaign_name", "") or "").lower() == campaign_name.lower()
            for campaign in user_campaigns
        )
        if not campaign_exists:
            raise HTTPException(status_code=404, detail=f"Campaign '{campaign_name}' not found for user '{username}'")
        
        # Fetch campaign responses using existing function
        campaign_data = fetch_campaign_responses(username, campaign_name)
        if not campaign_data:
            raise HTTPException(status_code=404, detail=f"No campaign data found for '{username}/{campaign_name}'")
        
        # Parse the campaign plan from the available responses
        campaign_plan = None
        
        # Try to get campaign plan from different sources in order of preference
        for response_key in ["approve_response", "approved_plan_v3", "approved_plan_v2", "approved_plan_v1", "plan_response"]:
            if campaign_data.get(response_key):
                try:
                    response_data = json.loads(campaign_data[response_key])
                    if "campaign_plan" in response_data:
                        campaign_plan = response_data["campaign_plan"]
                        break
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in {response_key} for {username}/{campaign_name}")
                    continue
        
        if not campaign_plan:
            raise HTTPException(status_code=404, detail=f"No valid campaign plan found for '{username}/{campaign_name}'")
        
        # Parse campaign plan if it's still a string
        if isinstance(campaign_plan, str):
            try:
                campaign_plan = json.loads(campaign_plan)
            except json.JSONDecodeError:
                logger.warning("Campaign plan is string but not valid JSON")
        
        # Add image data to campaign plan if requested
        if include_images:
            campaign_plan = add_images_to_campaign_plan(
                campaign_plan, username, campaign_name, image_format
            )
        
        # Build comprehensive response
        response_data = {
            "campaign_name": f"{username}/{campaign_name}",
            "success": True,
            "campaign_plan": campaign_plan,
            "include_images": include_images,
            "image_format": image_format if include_images else None,
            "retrieved_at": datetime.now().isoformat(),
            
            # Include all available responses
            "plan_response": json.loads(campaign_data["plan_response"]) if campaign_data.get("plan_response") else None,
            "approve_response": json.loads(campaign_data["approve_response"]) if campaign_data.get("approve_response") else None,
            "approved_plan_v1": json.loads(campaign_data["approved_plan_v1"]) if campaign_data.get("approved_plan_v1") else None,
            "approved_plan_v2": json.loads(campaign_data["approved_plan_v2"]) if campaign_data.get("approved_plan_v2") else None,
            "approved_plan_v3": json.loads(campaign_data["approved_plan_v3"]) if campaign_data.get("approved_plan_v3") else None,
            "human_feedback_v1": json.loads(campaign_data["human_feedback_v1"]) if campaign_data.get("human_feedback_v1") else None,
            "human_feedback_v2": json.loads(campaign_data["human_feedback_v2"]) if campaign_data.get("human_feedback_v2") else None,
            "human_feedback_v3": json.loads(campaign_data["human_feedback_v3"]) if campaign_data.get("human_feedback_v3") else None,
        }
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving campaign responses: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve campaign responses: Contact support team!")


def add_images_to_campaign_plan(
    campaign_plan: Dict[str, Any], 
    username: str, 
    campaign_name: str, 
    image_format: str
) -> Dict[str, Any]:
    """
    Add image data to campaign plan structure from database.
    
    Args:
        campaign_plan: The campaign plan dictionary
        username: User identifier
        campaign_name: Campaign identifier  
        image_format: "url" for imagePath format or "base64" for data URLs
    """
    try:
        # Get all images for this campaign from database
        campaign_images = get_campaign_images_from_db(username, campaign_name)
        
        if not campaign_images:
            logger.info(f"No images found for campaign {username}/{campaign_name}")
            return campaign_plan
        
        # Organize images by platform/week/day
        images_by_location = {}
        for img in campaign_images:
            location_key = f"{img['platform']}.{img['week_key']}.{img['day_key']}"
            if location_key not in images_by_location:
                images_by_location[location_key] = []
            images_by_location[location_key].append(img)
        
        # Add images to campaign plan structure
        for platform, weeks in campaign_plan.items():
            if not isinstance(weeks, dict):
                continue
                
            for week_key, days in weeks.items():
                if not isinstance(days, dict):
                    continue
                    
                for day_key, day_data in days.items():
                    if not isinstance(day_data, dict):
                        continue
                    
                    location_key = f"{platform}.{week_key}.{day_key}"
                    if location_key in images_by_location:
                        images = images_by_location[location_key]
                        
                        if image_format == "base64":
                            # Return images as base64 data URLs
                            image_data_urls = []
                            for img in images:
                                try:
                                    # Extract file extension for MIME type
                                    content_type = img.get('content_type', 'image/jpeg')
                                    base64_data = img.get('base64_data', '')
                                    
                                    if base64_data:
                                        data_url = f"data:{content_type};base64,{base64_data}"
                                        image_data_urls.append(data_url)
                                except Exception as e:
                                    logger.error(f"Error processing image to base64: {e}")
                                    continue
                            
                            day_data["images"] = image_data_urls
                        else:
                            # Use imagePath:// format as requested
                            image_paths = []
                            for img in images:
                                image_path = f"imagePath://campaign-{username}/{platform}/{day_key}_{img['filename']}"
                                image_paths.append(image_path)
                            
                            day_data["images"] = image_paths
        
        logger.info(f"Added images to campaign plan for {len(images_by_location)} locations")
        return campaign_plan
        
    except Exception as e:
        logger.error(f"Error adding images to campaign plan: {e}")
        return campaign_plan

# ========================= ADDITIONAL UTILITY ENDPOINTS =========================
# Optional: Add these utility endpoints for image management

@router.delete("/{username}/{campaign_name}/images/{platform}/{week_key}/{day_key}/{filename}")
async def delete_campaign_image_endpoint(
    username: str,
    campaign_name: str,
    platform: str,
    week_key: str,
    day_key: str,
    filename: str
):
    """Delete a specific campaign image."""
    try:
        # Validate user and campaign
        user_data = get_user_by_username(username)
        if not user_data:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
            
        user_campaigns = get_user_campaigns(username)
        campaign_exists = any(
            (campaign.get("campaign_name", "") or "").lower() == campaign_name.lower()
            for campaign in user_campaigns
        )
        if not campaign_exists:
            raise HTTPException(status_code=404, detail=f"Campaign '{campaign_name}' not found for user '{username}'")
        
        # Delete the image
        success = delete_campaign_image(username, campaign_name, filename, platform, week_key, day_key)
        
        if success:
            return {
                "success": True,
                "message": f"Image '{filename}' deleted successfully",
                "deleted_image": {
                    "filename": filename,
                    "platform": platform,
                    "week_key": week_key,
                    "day_key": day_key
                }
            }
        else:
            raise HTTPException(status_code=404, detail=f"Image '{filename}' not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting image: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete image: Contact support team!")


@router.get("/{username}/{campaign_name}/images/summary")
async def get_campaign_images_summary(
    username: str,
    campaign_name: str
):
    """Get summary of all images in a campaign."""
    try:
        # Validate user and campaign
        user_data = get_user_by_username(username)
        if not user_data:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
            
        user_campaigns = get_user_campaigns(username)
        campaign_exists = any(
            (campaign.get("campaign_name", "") or "").lower() == campaign_name.lower()
            for campaign in user_campaigns
        )
        if not campaign_exists:
            raise HTTPException(status_code=404, detail=f"Campaign '{campaign_name}' not found for user '{username}'")
        
        # Get all images
        campaign_images = get_campaign_images_from_db(username, campaign_name)
        
        # Organize summary by platform
        summary = {
            "total_images": len(campaign_images),
            "platforms": {},
            "total_size": 0
        }
        
        for img in campaign_images:
            platform = img.get('platform', 'unknown')
            if platform not in summary["platforms"]:
                summary["platforms"][platform] = {
                    "count": 0,
                    "total_size": 0,
                    "locations": []
                }
            
            summary["platforms"][platform]["count"] += 1
            summary["platforms"][platform]["total_size"] += img.get('file_size', 0)
            summary["total_size"] += img.get('file_size', 0)
            
            location = f"{img.get('week_key', 'unknown')}/{img.get('day_key', 'unknown')}"
            if location not in summary["platforms"][platform]["locations"]:
                summary["platforms"][platform]["locations"].append(location)
        
        return {
            "success": True,
            "campaign_name": f"{username}/{campaign_name}",
            "summary": summary,
            "retrieved_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting images summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get images summary: Contact support team!")

# ========================= INTEGRATION NOTES =========================
"""
INTEGRATION INSTRUCTIONS:

1. Add the additional imports to the top of your src/api/api.py file:
   - import base64
   - import mimetypes
   - import os
   - from PIL import Image
   - import io

2. Add all the database helper functions to your src/api/db_utils.py file:
   - get_existing_campaign_images()
   - get_campaign_images_from_db() 
   - get_images_for_location()
   - delete_campaign_image()

3. Add all the API endpoints to your existing router in src/api/api.py:
   - upload_campaign_images()
   - get_campaign_responses() (this replaces or extends your existing responses endpoint)
   - add_images_to_campaign_plan() (helper function)
   - delete_campaign_image_endpoint() (optional)
   - get_campaign_images_summary() (optional)

4. Install required dependency:
   pip install Pillow

5. Your existing database schema should already have the campaign_images column as TEXT/JSON.

USAGE:

Upload images:
POST /{username}/{campaign_name}/upload_images
- Form data: platform, week_key, day_key
- Files: Multiple image files

Get campaign with images:
GET /{username}/{campaign_name}/responses?include_images=true&image_format=url
GET /{username}/{campaign_name}/responses?include_images=true&image_format=base64

The system will:
- Store images as base64 in your existing campaign_images JSON column
- Return images in the exact format you requested:
  - imagePath:// format for URL mode
  - data:image/type;base64,... format for base64 mode
- Integrate seamlessly with your existing fetch_campaign_responses() function
- Preserve all existing functionality while adding image support
"""
