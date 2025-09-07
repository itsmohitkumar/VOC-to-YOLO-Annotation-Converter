        # Version == 0: approved_plan file
        if version == 0:
            key = f"{base_dir}/approved_plan.xlsx"
            try:
                obj = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
                data = obj["Body"].read()
                resp = StreamingResponse(io.BytesIO(data),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                resp.headers["Content-Disposition"] = 'attachment; filename="approved_plan.xlsx"'
                return resp
            except ClientError as e:
                if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                    raise HTTPException(status_code=404, detail="Approved plan file not found.")
                raise HTTPException(status_code=500, detail="Error retrieving file from S3.")
