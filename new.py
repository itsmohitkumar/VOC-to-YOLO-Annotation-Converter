@router.get("/{username}/{campaign_name}", response_class=StreamingResponse)
async def download_campaign_file(
    username: str,
    campaign_name: str,
    file_type: str = "plan",
    version: int | None = None
):
    """
    Download versioned campaign Excel.
    - If version > 0 provided, returns that exact version (404 if not found).
    - If version == 0, returns the non-versioned approved file.
    - If no version provided, returns the latest versioned file if available,
      otherwise falls back to the non-versioned file.
    """
    try:
        if file_type not in ("plan", "campaign"):
            raise HTTPException(status_code=400, detail="Invalid file_type. Must be 'plan' or 'campaign'.")
        base_clean = f"{username}_{campaign_name}"
        suffix = "_plan" if file_type == "plan" else "_final"
        base_dir = f"campaigns/{username}/{campaign_name}/campaign_planner/excel"

        # Explicit version > 0
        if version and version > 0:
            key = f"{base_dir}/{base_clean}{suffix}_v{version}.xlsx"
            try:
                obj = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
                data = obj["Body"].read()
                resp = StreamingResponse(io.BytesIO(data),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                resp.headers["Content-Disposition"] = f'attachment; filename="{base_clean}{suffix}_v{version}.xlsx"'
                return resp
            except ClientError as e:
                if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                    raise HTTPException(status_code=404, detail=f"{file_type.capitalize()} v{version} not found.")
                raise HTTPException(status_code=500, detail="Error retrieving file from S3.")

        # Version == 0: non-versioned approved file
        if version == 0:
            key = f"{base_dir}/{base_clean}{suffix}.xlsx"
            try:
                obj = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
                data = obj["Body"].read()
                resp = StreamingResponse(io.BytesIO(data),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                resp.headers["Content-Disposition"] = f'attachment; filename="{base_clean}{suffix}.xlsx"'
                return resp
            except ClientError as e:
                if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                    raise HTTPException(status_code=404, detail=f"{file_type.capitalize()} file not found.")
                raise HTTPException(status_code=500, detail="Error retrieving file from S3.")

        # No version specified: try latest version, then fallback
        prefix = f"{base_dir}/{base_clean}{suffix}_v"
        latest = _get_latest_versioned_key(S3_BUCKET, prefix)
        candidates = [latest, f"{base_dir}/{base_clean}{suffix}.xlsx"]
        for key in candidates:
            if not key:
                continue
            try:
                obj = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
                data = obj["Body"].read()
                fname = key.rsplit("/", 1)[-1]
                resp = StreamingResponse(io.BytesIO(data),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
                return resp
            except ClientError as e:
                if e.response["Error"]["Code"] not in ("NoSuchKey", "404"):
                    raise HTTPException(status_code=500, detail="Error retrieving file from S3.")
        raise HTTPException(status_code=404, detail=f"No {file_type} file found.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
