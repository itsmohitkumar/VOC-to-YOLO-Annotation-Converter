Here’s a complete sample campaign input you can use to test both the plan‐generation and feedback endpoints.

1. Register Campaign (POST /campaigns/register)  
```json
{
  "username": "acme_marketing",
  "campaign_name": "SummerLaunch2025",
  "location": "New York, USA",
  "campaign_voice": "Professional",
  "web_link": "https://acme.example.com",
  "supporting_web_link": "https://acme.example.com/whitepaper",
  "campaign_book": "Acme_Campaign_Book.pdf",
  "logo": "https://acme.example.com/logo.png"
}
```

2. Submit Campaign Plan (POST /{username}/{campaign_name}/plan)  
```json
{
  "campaign_name": "SummerLaunch2025",
  "campaign_objective": "Increase sign-ups for our new SaaS product",
  "campaign_description": "A 30-day campaign to drive trial registrations through social media channels",
  "start_date": "2025-06-01",
  "end_date": "2025-06-30",
  "target_audience": "IT decision-makers in mid-size enterprises",
  "target_audience_location": "USA",
  "target_audience_info": [
    "CIOs and IT managers",
    "Looking for cost-effective cloud solutions",
    "Prefer technical whitepapers and case studies"
  ],
  "platforms": ["instagram","facebook","x","email","sms"]
}
```

3. Approve Campaign Plan (POST /{username}/{campaign_name}/approve)  
```json
{
  "username": "acme_marketing",
  "campaign_name": "SummerLaunch2025"
}
```

4. Provide Feedback on a Post (POST /{username}/{campaign_name}/feedback)  
```json
{
  "feedbacks": [
    {
      "post_id": "instagram_week_1_Day_1",
      "feedback_text": "Great hook, but please add a statistic about cloud cost savings."
    },
    {
      "post_id": "email_week_2_Day_3",
      "feedback_text": "Subject line needs more urgency. Emphasize limited-time offer."
    }
  ]
}
```

Use these JSON bodies to exercise the full workflow end-to-end.

[1](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/42012257/3b7a7c38-422b-4f23-8b02-024b707c0a84/paste.txt)
