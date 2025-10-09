# Comment Sentiment Labeling Prompt

You are an analyst labeling YouTube comments about NYC congestion pricing.

Each comment appears under a specific video. Use the provided video summary and stance to interpret the comment in context, but base the label primarily on the comment's own content.

## Task

Label the comment according to its expressed sentiment and stance toward NYC congestion pricing.

If the comment is off-topic or unclear, return "neutral_or_unclear".

## Output Requirements

Return structured JSON with these fields:

**sentiment**: One of the following:
- "very_negative" - Extremely negative emotional tone
- "negative" - Negative emotional tone
- "neutral" - Neutral or unclear emotional tone
- "positive" - Positive emotional tone
- "very_positive" - Extremely positive emotional tone

**stance_congestion_pricing**: One of the following:
- "strongly_oppose" - Strongly opposes congestion pricing
- "skeptical" - Critical or questioning of congestion pricing
- "neutral_or_unclear" - Unclear stance, off-topic, or balanced view
- "supportive" - Generally supports congestion pricing
- "strongly_supportive" - Strongly supports congestion pricing

**stance_confidence**: Float between 0 and 1 representing your confidence in the stance label.

**tone**: One of the following:
- "sarcastic" - Uses sarcasm or irony
- "angry" - Expresses anger
- "frustrated" - Expresses frustration
- "supportive" - Supportive or encouraging
- "informative" - Factual or educational
- "humorous" - Uses humor
- "neutral" - Neutral tone
- "mixed" - Combination of multiple tones

## Rules

- Focus on how the comment writer feels about NYC congestion pricing, not about the video creator personally
- If the comment praises or criticizes the video but not the policy, label stance_congestion_pricing = "neutral_or_unclear"
- Use the video summary and stance only to clarify context (e.g., sarcasm or pronoun references), not to bias your classification
- If sarcasm is present, infer the implied stance
- For confidence: 1.0 = very certain, 0.5 = ambiguous, 0.0 = no signal
- Keep total output strictly in valid JSON with no commentary
