

# Image upload settings
SUPPORTED_IMAGE_FORMATS = ["jpg", "jpeg", "png", "gif", "webp", "bmp"]
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
IMAGE_OPTIMIZATION_QUALITY = 85
MAX_IMAGE_WIDTH = 1080

# Modified get_campaign_responses API with base64 image support

@router.get("/{username}/{campaign_name}/responses", response_model=dict)
async def get_campaign_responses(
    username: str, 
    campaign_name: str,
    include_images: bool = False
):
    """
    Endpoint to retrieve the responses (plan_response, approve_response, feedback_response,
    and the approved plan versions) for a specific campaign and user.
    
    Args:
        username: Username of the campaign owner
        campaign_name: Name of the campaign  
        include_images: Whether to include base64 image data (default: False for performance)
    """
    try:
        responses = fetch_campaign_responses(username, campaign_name)
        if responses:
            # List all keys that store JSON strings to parse
            json_fields = [
                "plan_response",
                "approve_response", 
                "feedback_response",
                "approved_plan_v1",
                "approved_plan_v2",
                "approved_plan_v3",
                "human_feedback_v1",
                "human_feedback_v2",
                "human_feedback_v3"
            ]
            
            for key in json_fields:
                if key in responses and responses.get(key):
                    try:
                        responses[key] = json.loads(responses[key])
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse {key} into JSON format for user '{username}' in campaign '{campaign_name}'")
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to parse the {key} into JSON format."
                        )
            
            # Add base64 images if requested
            if include_images:
                responses = await add_base64_images_to_responses(responses, username, campaign_name)
            
            return responses
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No campaign found for user '{username}' with campaign name '{campaign_name}'"
            )
    except HTTPException:
        raise  # Re-raise HTTPException
    except Exception as e:
        logger.error(f"Failed to retrieve responses for user '{username}' in campaign '{campaign_name}': {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve responses for user '{username}' in campaign '{campaign_name}': {str(e)}"
        )

async def add_base64_images_to_responses(
    responses: Dict[str, Any], 
    username: str, 
    campaign_name: str
) -> Dict[str, Any]:
    """
    Add base64 image data to campaign responses for posts that have images.
    
    Args:
        responses: Campaign responses dictionary
        username: Username of the campaign owner
        campaign_name: Name of the campaign
        
    Returns:
        Updated responses with base64 image data
    """
    try:
        # Keys that might contain campaign plans with images
        plan_keys = [
            "approve_response",
            "approved_plan_v1", 
            "approved_plan_v2",
            "approved_plan_v3",
            "feedback_response"
        ]
        
        for key in plan_keys:
            if key in responses and responses[key]:
                try:
                    plan_data = responses[key]
                    
                    # Handle feedback_response which has nested structure
                    if key == "feedback_response" and "approved_plan" in plan_data:
                        campaign_plan = plan_data["approved_plan"].get("campaign_plan", {})
                    else:
                        campaign_plan = plan_data.get("campaign_plan", {})
                    
                    if campaign_plan:
                        # Add base64 images to campaign plan
                        updated_plan = await add_base64_to_campaign_plan(campaign_plan)
                        
                        # Update the responses with base64 data
                        if key == "feedback_response" and "approved_plan" in plan_data:
                            responses[key]["approved_plan"]["campaign_plan"] = updated_plan
                        else:
                            responses[key]["campaign_plan"] = updated_plan
                            
                except Exception as e:
                    logger.error(f"Error adding base64 images to {key}: {e}")
                    # Continue with other keys if one fails
                    continue
        
        return responses
        
    except Exception as e:
        logger.error(f"Error adding base64 images to responses: {e}")
        return responses  # Return original responses if error occurs

async def add_base64_to_campaign_plan(campaign_plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add base64 image data to posts in campaign plan that have S3 image URLs.
    
    Args:
        campaign_plan: Campaign plan dictionary
        
    Returns:
        Updated campaign plan with base64 image data
    """
    try:
        updated_plan = campaign_plan.copy()
        
        # Iterate through all posts in campaign plan
        for platform, weeks in updated_plan.items():
            if isinstance(weeks, dict):
                for week, days in weeks.items():
                    if isinstance(days, dict):
                        for day, post_data in days.items():
                            if isinstance(post_data, dict) and "image_s3_url" in post_data:
                                try:
                                    # Get base64 image from S3
                                    s3_url = post_data["image_s3_url"]
                                    base64_image = get_image_base64_from_s3(s3_url)
                                    post_data["image_base64"] = base64_image
                                    
                                    # Add metadata
                                    post_data["image_loaded"] = True
                                    post_data["image_load_timestamp"] = datetime.utcnow().isoformat()
                                    
                                except Exception as e:
                                    logger.error(f"Error loading base64 for {platform}_{week}_{day}: {e}")
                                    post_data["image_base64"] = None
                                    post_data["image_loaded"] = False
                                    post_data["image_error"] = str(e)
        
        return updated_plan
        
    except Exception as e:
        logger.error(f"Error processing campaign plan for base64 images: {e}")
        return campaign_plan  # Return original if error occurs

def get_image_base64_from_s3(s3_url: str) -> str:
    """
    Retrieve image from S3 and convert to base64.
    
    Args:
        s3_url: S3 URL of the image
        
    Returns:
        Base64 encoded image string with data URL prefix
    """
    try:
        # Extract bucket and key from S3 URL
        s3_parts = s3_url.replace('s3://', '').split('/', 1)
        bucket = s3_parts[0]
        key = s3_parts[1]
        
        # Download from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        image_content = response['Body'].read()
        
        # Convert to base64
        base64_image = base64.b64encode(image_content).decode('utf-8')
        return f"data:image/jpeg;base64,{base64_image}"
        
    except Exception as e:
        logger.error(f"Error retrieving image from S3 {s3_url}: {e}")
        raise Exception(f"Failed to retrieve image from S3: {str(e)}")

# Additional helper endpoint to get images summary
@router.get("/{username}/{campaign_name}/images-summary")
async def get_campaign_images_summary(username: str, campaign_name: str) -> Dict[str, Any]:
    """
    Get a summary of all images in the campaign without base64 data (for performance).
    
    Args:
        username: Username of the campaign owner
        campaign_name: Name of the campaign
        
    Returns:
        Summary of images by post_id
    """
    try:
        responses = fetch_campaign_responses(username, campaign_name)
        if not responses:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        images_summary = {}
        total_images = 0
        
        # Parse JSON fields and look for images
        json_fields = ["approve_response", "approved_plan_v1", "approved_plan_v2", "approved_plan_v3", "feedback_response"]
        
        for key in json_fields:
            if key in responses and responses[key]:
                try:
                    plan_data = json.loads(responses[key]) if isinstance(responses[key], str) else responses[key]
                    
                    # Handle different response structures
                    if key == "feedback_response" and "approved_plan" in plan_data:
                        campaign_plan = plan_data["approved_plan"].get("campaign_plan", {})
                    else:
                        campaign_plan = plan_data.get("campaign_plan", {})
                    
                    # Extract image info
                    for platform, weeks in campaign_plan.items():
                        if isinstance(weeks, dict):
                            for week, days in weeks.items():
                                if isinstance(days, dict):
                                    for day, post_data in days.items():
                                        if isinstance(post_data, dict) and "image_s3_url" in post_data:
                                            post_id = f"{platform}_{week}_{day}"
                                            images_summary[post_id] = {
                                                "s3_url": post_data["image_s3_url"],
                                                "filename": post_data.get("image_filename", ""),
                                                "upload_timestamp": post_data.get("image_upload_timestamp", ""),
                                                "size": post_data.get("image_size", 0),
                                                "source_version": key
                                            }
                                            total_images += 1
                
                except Exception as e:
                    logger.error(f"Error parsing {key} for images: {e}")
                    continue
        
        return {
            "success": True,
            "campaign_name": f"{username}/{campaign_name}",
            "total_images": total_images,
            "images_summary": images_summary,
            "message": f"Found {total_images} images across all campaign versions"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting images summary: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving images summary")



# Modified get_campaign_responses API with base64 image support

@router.get("/{username}/{campaign_name}/responses", response_model=dict)
async def get_campaign_responses(
    username: str, 
    campaign_name: str,
    include_images: bool = False
):
    """
    Endpoint to retrieve the responses (plan_response, approve_response, feedback_response,
    and the approved plan versions) for a specific campaign and user.
    
    Args:
        username: Username of the campaign owner
        campaign_name: Name of the campaign  
        include_images: Whether to include base64 image data (default: False for performance)
    """
    try:
        responses = fetch_campaign_responses(username, campaign_name)
        if responses:
            # List all keys that store JSON strings to parse
            json_fields = [
                "plan_response",
                "approve_response", 
                "feedback_response",
                "approved_plan_v1",
                "approved_plan_v2",
                "approved_plan_v3",
                "human_feedback_v1",
                "human_feedback_v2",
                "human_feedback_v3"
            ]
            
            for key in json_fields:
                if key in responses and responses.get(key):
                    try:
                        responses[key] = json.loads(responses[key])
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse {key} into JSON format for user '{username}' in campaign '{campaign_name}'")
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to parse the {key} into JSON format."
                        )
            
            # Add base64 images if requested
            if include_images:
                responses = await add_base64_images_to_responses(responses, username, campaign_name)
            
            return responses
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No campaign found for user '{username}' with campaign name '{campaign_name}'"
            )
    except HTTPException:
        raise  # Re-raise HTTPException
    except Exception as e:
        logger.error(f"Failed to retrieve responses for user '{username}' in campaign '{campaign_name}': {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve responses for user '{username}' in campaign '{campaign_name}': {str(e)}"
        )

async def add_base64_images_to_responses(
    responses: Dict[str, Any], 
    username: str, 
    campaign_name: str
) -> Dict[str, Any]:
    """
    Add base64 image data to campaign responses for posts that have images.
    
    Args:
        responses: Campaign responses dictionary
        username: Username of the campaign owner
        campaign_name: Name of the campaign
        
    Returns:
        Updated responses with base64 image data
    """
    try:
        # Keys that might contain campaign plans with images
        plan_keys = [
            "approve_response",
            "approved_plan_v1", 
            "approved_plan_v2",
            "approved_plan_v3",
            "feedback_response"
        ]
        
        for key in plan_keys:
            if key in responses and responses[key]:
                try:
                    plan_data = responses[key]
                    
                    # Handle feedback_response which has nested structure
                    if key == "feedback_response" and "approved_plan" in plan_data:
                        campaign_plan = plan_data["approved_plan"].get("campaign_plan", {})
                    else:
                        campaign_plan = plan_data.get("campaign_plan", {})
                    
                    if campaign_plan:
                        # Add base64 images to campaign plan
                        updated_plan = await add_base64_to_campaign_plan(campaign_plan)
                        
                        # Update the responses with base64 data
                        if key == "feedback_response" and "approved_plan" in plan_data:
                            responses[key]["approved_plan"]["campaign_plan"] = updated_plan
                        else:
                            responses[key]["campaign_plan"] = updated_plan
                            
                except Exception as e:
                    logger.error(f"Error adding base64 images to {key}: {e}")
                    # Continue with other keys if one fails
                    continue
        
        return responses
        
    except Exception as e:
        logger.error(f"Error adding base64 images to responses: {e}")
        return responses  # Return original responses if error occurs

async def add_base64_to_campaign_plan(campaign_plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add base64 image data to posts in campaign plan that have S3 image URLs.
    
    Args:
        campaign_plan: Campaign plan dictionary
        
    Returns:
        Updated campaign plan with base64 image data
    """
    try:
        updated_plan = campaign_plan.copy()
        
        # Iterate through all posts in campaign plan
        for platform, weeks in updated_plan.items():
            if isinstance(weeks, dict):
                for week, days in weeks.items():
                    if isinstance(days, dict):
                        for day, post_data in days.items():
                            if isinstance(post_data, dict) and "image_s3_url" in post_data:
                                try:
                                    # Get base64 image from S3
                                    s3_url = post_data["image_s3_url"]
                                    base64_image = get_image_base64_from_s3(s3_url)
                                    post_data["image_base64"] = base64_image
                                    
                                    # Add metadata
                                    post_data["image_loaded"] = True
                                    post_data["image_load_timestamp"] = datetime.utcnow().isoformat()
                                    
                                except Exception as e:
                                    logger.error(f"Error loading base64 for {platform}_{week}_{day}: {e}")
                                    post_data["image_base64"] = None
                                    post_data["image_loaded"] = False
                                    post_data["image_error"] = str(e)
        
        return updated_plan
        
    except Exception as e:
        logger.error(f"Error processing campaign plan for base64 images: {e}")
        return campaign_plan  # Return original if error occurs

def get_image_base64_from_s3(s3_url: str) -> str:
    """
    Retrieve image from S3 and convert to base64.
    
    Args:
        s3_url: S3 URL of the image
        
    Returns:
        Base64 encoded image string with data URL prefix
    """
    try:
        # Extract bucket and key from S3 URL
        s3_parts = s3_url.replace('s3://', '').split('/', 1)
        bucket = s3_parts[0]
        key = s3_parts[1]
        
        # Download from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        image_content = response['Body'].read()
        
        # Convert to base64
        base64_image = base64.b64encode(image_content).decode('utf-8')
        return f"data:image/jpeg;base64,{base64_image}"
        
    except Exception as e:
        logger.error(f"Error retrieving image from S3 {s3_url}: {e}")
        raise Exception(f"Failed to retrieve image from S3: {str(e)}")

# Additional helper endpoint to get images summary
@router.get("/{username}/{campaign_name}/images-summary")
async def get_campaign_images_summary(username: str, campaign_name: str) -> Dict[str, Any]:
    """
    Get a summary of all images in the campaign without base64 data (for performance).
    
    Args:
        username: Username of the campaign owner
        campaign_name: Name of the campaign
        
    Returns:
        Summary of images by post_id
    """
    try:
        responses = fetch_campaign_responses(username, campaign_name)
        if not responses:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        images_summary = {}
        total_images = 0
        
        # Parse JSON fields and look for images
        json_fields = ["approve_response", "approved_plan_v1", "approved_plan_v2", "approved_plan_v3", "feedback_response"]
        
        for key in json_fields:
            if key in responses and responses[key]:
                try:
                    plan_data = json.loads(responses[key]) if isinstance(responses[key], str) else responses[key]
                    
                    # Handle different response structures
                    if key == "feedback_response" and "approved_plan" in plan_data:
                        campaign_plan = plan_data["approved_plan"].get("campaign_plan", {})
                    else:
                        campaign_plan = plan_data.get("campaign_plan", {})
                    
                    # Extract image info
                    for platform, weeks in campaign_plan.items():
                        if isinstance(weeks, dict):
                            for week, days in weeks.items():
                                if isinstance(days, dict):
                                    for day, post_data in days.items():
                                        if isinstance(post_data, dict) and "image_s3_url" in post_data:
                                            post_id = f"{platform}_{week}_{day}"
                                            images_summary[post_id] = {
                                                "s3_url": post_data["image_s3_url"],
                                                "filename": post_data.get("image_filename", ""),
                                                "upload_timestamp": post_data.get("image_upload_timestamp", ""),
                                                "size": post_data.get("image_size", 0),
                                                "source_version": key
                                            }
                                            total_images += 1
                
                except Exception as e:
                    logger.error(f"Error parsing {key} for images: {e}")
                    continue
        
        return {
            "success": True,
            "campaign_name": f"{username}/{campaign_name}",
            "total_images": total_images,
            "images_summary": images_summary,
            "message": f"Found {total_images} images across all campaign versions"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting images summary: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving images summary")
