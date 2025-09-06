from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import json
import copy
import hashlib
from datetime import datetime
from src.models import MultiFeedbackRequest, State
from .db_utils import fetch_campaign_responses, update_agentic_campaign_planner
from .agent_graph import system_agents
from utils.logger import logger

router = APIRouter()

@router.post("/{username}/{campaign_name}/feedback")
async def submit_feedback(
    username: str,
    campaign_name: str,
    feedback_request: MultiFeedbackRequest
) -> Dict[str, Any]:
    """
    Batch feedback regeneration loading the stored plan from the database.
    - Accepts list of feedback items: [{post_id, feedback_text}, ...]
    - Applies feedback to the stored plan_response.campaign_plan
    - Persists feedback_response and approved_plan_v{batch_version} in the DB
    """
    try:
        full_name = f"{username}/{campaign_name}"
        logger.info(f"Processing feedback for {full_name}")

        # Validate user & campaign
        user_campaigns = get_user_campaigns(username)
        if not any(c.get("campaign_name", "").lower() == campaign_name.lower() for c in user_campaigns):
            raise HTTPException(404, "Campaign not found")

        # Deduplicate feedback items
        deduped = []
        seen = set()
        for fb in feedback_request.feedbacks or []:
            pid = fb.post_id.strip().lower()
            if pid and pid not in seen:
                seen.add(pid)
                deduped.append(fb)
        if not deduped:
            raise HTTPException(400, "No valid feedback items provided")

        # 1. Load stored plan_response from DB
        db_resp = fetch_campaign_responses(username, campaign_name)
        if not db_resp or not db_resp.get("plan_response"):
            raise HTTPException(404, "No stored plan_response found")
        plan_obj = db_resp["plan_response"]
        if isinstance(plan_obj, str):
            try:
                plan_obj = json.loads(plan_obj)
            except json.JSONDecodeError:
                raise HTTPException(500, "Invalid stored plan_response JSON")

        # Extract campaign_plan dict
        campaign_plan = plan_obj.get("campaign_plan")
        if isinstance(campaign_plan, str):
            campaign_plan = json.loads(campaign_plan)

        # Prepare feedback tracking structure
        feedback_dict = {
            "campaign_name": full_name,
            "feedback_history": [],
            "current_regen_attempts": {},
            "approved_plan_versions": [],
            "previous_variants": {}
        }

        details: Dict[str, Any] = {}
        human_map: Dict[str, str] = {}

        # Helper functions
        def classify_strength(text: str) -> str:
            t = text.lower()
            if any(k in t for k in ["completely rewrite", "start over"]):
                return "strong"
            if any(k in t for k in ["improve", "better", "enhance"]):
                return "medium"
            return "light"

        def progressive_temp(attempt: int, strength: str) -> float:
            base = {"light": 0.8, "medium": 0.85, "strong": 0.9}[strength]
            return min(base + 0.1 * (attempt - 1), 0.95)

        def make_seed(pid: str, attempt: int, text: str) -> str:
            return hashlib.sha256(f"{pid}|{attempt}|{text[:50]}".encode()).hexdigest()

        def apply_injection():
            # No-op: final updated campaign_plan will replace stored one
            pass

        # 2. Process each feedback item
        for fb in deduped:
            pid = fb.post_id.strip().lower()
            feedback_text = fb.feedback_text.strip()
            human_map[pid] = feedback_text

            # Track attempts
            curr = feedback_dict["current_regen_attempts"].get(pid, 0) + 1
            feedback_dict["current_regen_attempts"][pid] = curr
            feedback_dict["feedback_history"].append({
                "post_id": pid,
                "feedback_text": feedback_text,
                "attempt": curr,
                "timestamp": datetime.utcnow().isoformat()
            })

            strength = classify_strength(feedback_text)
            temp = progressive_temp(curr, strength)
            seed = make_seed(pid, curr, feedback_text)

            # Build state for regeneration
            state = State(
                campaign_name=full_name,
                campaign_plan=campaign_plan,
                plan_approved=True,
                stage="content_generation",
                current_post_id=pid,
                regen_attempt_number=curr,
                human_feedback_text=feedback_text,
                feedback_strength=strength,
                temperature_override=temp,
                random_seed=seed,
                previous_variants=feedback_dict["previous_variants"]
            )

            # Invoke regeneration
            final_state = await system_agents.ainvoke(state)
            result_plan = dict(final_state).get("campaign_plan", {})

            # Update campaign_plan in place
            campaign_plan.update(result_plan)
            feedback_dict["previous_variants"].setdefault(pid, []).append({
                "content": campaign_plan.get(pid, {}),
                "attempt": curr,
                "timestamp": datetime.utcnow().isoformat()
            })
            details[pid] = {"success": True, "attempt": curr}

        # 3. Build approved_plan_data
        batch_version = max(feedback_dict["current_regen_attempts"].values(), default=1)
        approved_plan_data = {
            **plan_obj,
            "campaign_plan": campaign_plan,
            "feedback_map": human_map,
            "batch_version": batch_version,
            "excel_s3_url": None  # set if you upload Excel here
        }

        # 4. Persist feedback_response and approved_plan_v{n}
        update_agentic_campaign_planner(
            username=username,
            campaign_name=campaign_name,
            feedback_response=json.dumps({
                "feedback": feedback_dict,
                "approved_plan": approved_plan_data,
                "details": details
            }, ensure_ascii=False),
            **{f"approved_plan_v{batch_version}": json.dumps(approved_plan_data, ensure_ascii=False)}
        )

        # 5. Return response
        return {
            "campaign_name": full_name,
            "success": True,
            "batch_version": batch_version,
            "approved_plan": approved_plan_data,
            "details": details
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in submit_feedback: {e}")
        raise HTTPException(500, "Error processing feedback")
