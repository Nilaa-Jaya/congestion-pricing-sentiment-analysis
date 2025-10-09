#!/usr/bin/env python3
"""
Label YouTube comments with sentiment scores using OpenAI API.
Uses video summaries as context for more accurate sentiment analysis.
Includes rate limiting, progress checkpointing, and resume capability.
"""

import os
import csv
import argparse
import json
import time
from datetime import datetime
from typing import Literal
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
import pandas as pd

# Load environment variables
load_dotenv()


class CommentSentiment(BaseModel):
	"""Pydantic model for structured comment sentiment output"""
	sentiment: Literal["very_negative", "negative", "neutral", "positive", "very_positive"]
	stance_congestion_pricing: Literal["strongly_oppose", "skeptical", "neutral_or_unclear", "supportive", "strongly_supportive"]
	stance_confidence: float
	tone: Literal["sarcastic", "angry", "frustrated", "supportive", "informative", "humorous", "neutral", "mixed"]

# Rate limiting configuration
REQUESTS_PER_MINUTE = 50
DELAY_BETWEEN_REQUESTS = 60.0 / REQUESTS_PER_MINUTE  # ~1.2 seconds

# Checkpoint configuration
CHECKPOINT_INTERVAL = 100  # Save progress every N comments


def load_prompt(prompt_file):
	"""
	Load prompt text from markdown file.

	Args:
		prompt_file: Path to prompt file

	Returns:
		Prompt text as string
	"""
	with open(prompt_file, "r", encoding="utf-8") as f:
		return f.read()


def load_data(comments_file=None, summaries_file=None):
	"""
	Load comments and video summaries, then join them.

	Args:
		comments_file: Path to comments CSV (default: latest in data/)
		summaries_file: Path to summaries CSV (default: latest in data/)

	Returns:
		Joined DataFrame with comments and summaries
	"""
	try:
		# Load comments
		if comments_file is None:
			import glob
			csv_files = glob.glob("data/youtube_comments_*.csv")
			if not csv_files:
				print("Error: No comments CSV files found in data/ directory")
				return None
			comments_file = max(csv_files, key=os.path.getmtime)
			print(f"Loading comments from: {comments_file}")

		comments_df = pd.read_csv(comments_file)

		# Load summaries
		if summaries_file is None:
			import glob
			csv_files = glob.glob("data/video_summaries_*.csv")
			if not csv_files:
				print("Error: No summaries CSV files found in data/ directory")
				print("Please run summarize_videos.py first")
				return None
			summaries_file = max(csv_files, key=os.path.getmtime)
			print(f"Loading summaries from: {summaries_file}")

		summaries_df = pd.read_csv(summaries_file)

		# Join comments with summaries (get video stance and summary)
		df = comments_df.merge(
			summaries_df[["video_id", "summary_text", "stance_congestion_pricing", "stance_confidence"]],
			on="video_id",
			how="left"
		)

		# Check for missing summaries
		missing_summaries = df["summary_text"].isna().sum()
		if missing_summaries > 0:
			print(f"Warning: {missing_summaries} comments have no corresponding video summary")

		return df

	except Exception as e:
		print(f"Error loading data: {e}")
		return None


def label_sentiment(client, prompt, comment_text, video_context):
	"""
	Label a comment's sentiment using OpenAI API with structured outputs.

	Args:
		client: OpenAI client instance
		prompt: System prompt for sentiment labeling
		comment_text: Comment text
		video_context: Dict with video metadata (title, channel, published_at, stance, confidence, summary)

	Returns:
		CommentSentiment object or None if error
	"""
	try:
		user_message = f"""VIDEO CONTEXT
- Title: {video_context['video_title']}
- Channel: {video_context['video_channel']}
- Published: {video_context['video_published_at']}
- Video stance (prior): {video_context['stance_congestion_pricing']}
- Video stance confidence: {video_context['stance_confidence']}
- Video summary (≈200–300 words):
{video_context['summary_text']}

COMMENT
"{comment_text}"
"""

		response = client.responses.parse(
			model="gpt-4o-mini",
			input=[
				{"role": "system", "content": prompt},
				{"role": "user", "content": user_message}
			],
			text_format=CommentSentiment
		)
		return response.output_parsed

	except Exception as e:
		print(f"    Error calling OpenAI API: {e}")
		return None


def load_checkpoint(output_file):
	"""
	Load existing results to support resume capability.

	Args:
		output_file: Path to output CSV file

	Returns:
		Set of already-processed row indices
	"""
	if not os.path.exists(output_file):
		return set()

	try:
		df = pd.read_csv(output_file)
		# Assuming we added a row_index column
		if "row_index" in df.columns:
			return set(df["row_index"].tolist())
		return set()
	except Exception as e:
		print(f"Warning: Could not load checkpoint: {e}")
		return set()


def save_checkpoint(output_file, results, fieldnames):
	"""
	Save current results to CSV (checkpoint).

	Args:
		output_file: Path to output CSV file
		results: List of result dictionaries
		fieldnames: CSV column names
	"""
	try:
		with open(output_file, "w", newline="", encoding="utf-8") as f:
			writer = csv.DictWriter(f, fieldnames=fieldnames)
			writer.writeheader()
			writer.writerows(results)
		print(f"  Checkpoint saved ({len(results)} comments processed)")
	except Exception as e:
		print(f"  Warning: Could not save checkpoint: {e}")


def label_comments(comments_file=None, summaries_file=None, output_file=None, max_comments=None):
	"""
	Label all comments with sentiment scores.

	Args:
		comments_file: Path to comments CSV (default: latest in data/)
		summaries_file: Path to summaries CSV (default: latest in data/)
		output_file: Output CSV filename (default: data/labeled_comments_YYYYMMDD_HHMM.csv)
		max_comments: Maximum number of comments to process (default: all)
	"""
	# Check for API key
	api_key = os.getenv("OPENAI_API_KEY")
	if not api_key:
		print("Error: OPENAI_API_KEY not found in environment variables")
		print("Please add it to your .env file")
		return

	# Initialize OpenAI client
	client = OpenAI(api_key=api_key)

	# Load prompt
	prompt_file = "prompts/label_sentiment.md"
	if not os.path.exists(prompt_file):
		print(f"Error: Prompt file '{prompt_file}' not found")
		return

	print("Loading prompt...")
	prompt = load_prompt(prompt_file)

	# Load data
	print("Loading data...")
	df = load_data(comments_file, summaries_file)
	if df is None:
		return

	# Create data directory if it doesn't exist
	os.makedirs("data", exist_ok=True)

	# Generate default filename with timestamp if not provided
	if output_file is None:
		timestamp = datetime.now().strftime("%Y%m%d_%H%M")
		output_file = f"data/labeled_comments_{timestamp}.csv"

	# Add row index for tracking
	df["row_index"] = range(len(df))

	# Limit number of comments if specified
	if max_comments is not None and max_comments > 0:
		df = df.head(max_comments)
		print(f"Processing first {len(df)} comments (limited by --max-comments)")
	else:
		print(f"Processing {len(df)} comments...")

	# Load checkpoint to support resume
	processed_indices = load_checkpoint(output_file)
	if processed_indices:
		print(f"Found existing results: {len(processed_indices)} comments already processed")

	# Prepare fieldnames for output
	fieldnames = df.columns.tolist() + ["sentiment", "stance_congestion_pricing_comment", "stance_confidence_comment", "tone"]

	# Process comments
	results = []
	skipped = 0

	for i, row in df.iterrows():
		row_index = row["row_index"]

		# Skip if already processed
		if row_index in processed_indices:
			skipped += 1
			continue

		comment_text = row.get("comment_text", "")
		summary_text = row.get("summary_text", "")

		# Skip if missing data
		if pd.isna(comment_text) or pd.isna(summary_text):
			print(f"[{i+1}/{len(df)}] Skipping row {row_index} (missing data)")
			continue

		# Prepare video context
		video_context = {
			"video_title": row.get("video_title", ""),
			"video_channel": row.get("video_channel", ""),
			"video_published_at": row.get("video_published_at", ""),
			"stance_congestion_pricing": row.get("stance_congestion_pricing", ""),
			"stance_confidence": row.get("stance_confidence", ""),
			"summary_text": summary_text
		}

		print(f"[{i+1}/{len(df)}] Labeling comment from video {row['video_id']}")

		# Call API
		label = label_sentiment(client, prompt, comment_text, video_context)

		if label:
			result = row.to_dict()
			result["sentiment"] = label.sentiment
			result["stance_congestion_pricing_comment"] = label.stance_congestion_pricing
			result["stance_confidence_comment"] = label.stance_confidence
			result["tone"] = label.tone
			results.append(result)
			print(f"  → Sentiment: {label.sentiment}, Stance: {label.stance_congestion_pricing}, Confidence: {label.stance_confidence:.2f}")
		else:
			print(f"  → Failed to label comment")

		# Rate limiting
		time.sleep(DELAY_BETWEEN_REQUESTS)

		# Checkpoint
		if len(results) % CHECKPOINT_INTERVAL == 0:
			save_checkpoint(output_file, results, fieldnames)

	# Final save
	if results:
		save_checkpoint(output_file, results, fieldnames)
		print(f"\n Successfully labeled {len(results)} comments")
		if skipped > 0:
			print(f" Skipped {skipped} already-processed comments")
		print(f" Saved to: {output_file}")
	else:
		print("No comments labeled.")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(
		description="Label YouTube comments with sentiment scores using OpenAI API"
	)
	parser.add_argument(
		"-c",
		"--comments",
		type=str,
		default=None,
		help="Input comments CSV file (default: latest file in data/)",
	)
	parser.add_argument(
		"-s",
		"--summaries",
		type=str,
		default=None,
		help="Input summaries CSV file (default: latest file in data/)",
	)
	parser.add_argument(
		"-o",
		"--output",
		type=str,
		default=None,
		help="Output CSV filename (default: data/labeled_comments_YYYYMMDD_HHMM.csv)",
	)
	parser.add_argument(
		"-n",
		"--max-comments",
		type=int,
		default=None,
		help="Maximum number of comments to process (default: all)",
	)

	args = parser.parse_args()
	label_comments(args.comments, args.summaries, args.output, args.max_comments)
