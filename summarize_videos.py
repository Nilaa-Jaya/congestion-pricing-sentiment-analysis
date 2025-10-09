#!/usr/bin/env python3
"""
Summarize video transcripts using OpenAI API.
Generates concise summaries for each video to provide context for comment analysis.
"""

import os
import csv
import argparse
from datetime import datetime
from typing import Literal
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
import pandas as pd

# Load environment variables
load_dotenv()


class VideoSummary(BaseModel):
    """Pydantic model for structured video summary output"""

    summary_text: str
    stance_congestion_pricing: Literal[
        "strongly_supportive",
        "supportive",
        "neutral_or_mixed",
        "skeptical",
        "strongly_oppose",
        "unclear",
    ]
    stance_confidence: float
    key_arguments: list[str]
    tone: Literal[
        "objective", "persuasive", "critical", "humorous", "emotional", "mixed"
    ]


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


def load_transcripts(csv_file=None):
    """
    Load transcripts from CSV file.

    Args:
            csv_file: Path to transcripts CSV (default: latest file in data/)

    Returns:
            pandas DataFrame with transcripts
    """
    try:
        # If no file specified, find the latest transcripts CSV in data/
        if csv_file is None:
            import glob

            csv_files = glob.glob("data/transcripts_*.csv")
            if not csv_files:
                print("Error: No transcripts CSV files found in data/ directory")
                return None
            csv_file = max(csv_files, key=os.path.getmtime)
            print(f"Loading transcripts from: {csv_file}")

        df = pd.read_csv(csv_file)
        return df

    except FileNotFoundError:
        print(f"Error: File '{csv_file}' not found")
        return None
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return None


def load_comments(csv_file=None):
    """
    Load comments to get video metadata.

    Args:
            csv_file: Path to comments CSV (default: latest file in data/)

    Returns:
            pandas DataFrame with video metadata
    """
    try:
        # If no file specified, find the latest comments CSV in data/
        if csv_file is None:
            import glob

            csv_files = glob.glob("data/youtube_comments_*.csv")
            if not csv_files:
                print("Error: No comments CSV files found in data/ directory")
                return None
            csv_file = max(csv_files, key=os.path.getmtime)
            print(f"Loading video metadata from: {csv_file}")

        df = pd.read_csv(csv_file)

        # Get unique video metadata
        video_metadata = (
            df.groupby("video_id")
            .first()[
                [
                    "video_title",
                    "video_channel",
                    "video_published_at",
                    "video_description",
                ]
            ]
            .reset_index()
        )

        return video_metadata

    except FileNotFoundError:
        print(f"Error: File '{csv_file}' not found")
        return None
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return None


def summarize_video(client, prompt, video_metadata, transcript):
    """
    Generate structured summary for a video using OpenAI API.

    Args:
            client: OpenAI client instance
            prompt: System prompt for summarization
            video_metadata: Dict with video_title, video_channel, video_published_at, video_description
            transcript: Video transcript text

    Returns:
            VideoSummary object or None if error
    """
    try:
        # Format user message with all metadata
        user_message = f"""VIDEO METADATA
- Title: {video_metadata["video_title"]}
- Channel: {video_metadata["video_channel"]}
- Publish Date: {video_metadata["video_published_at"]}
- Description: {video_metadata["video_description"]}

TRANSCRIPT
{transcript}"""

        response = client.responses.parse(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message},
            ],
            text_format=VideoSummary,
        )
        return response.output_parsed

    except Exception as e:
        print(f"  Error calling OpenAI API: {e}")
        return None


def summarize_videos(transcripts_file=None, output_file=None):
    """
    Generate summaries for all videos in the transcripts CSV.

    Args:
            transcripts_file: Path to transcripts CSV (default: latest in data/)
            output_file: Output CSV filename (default: data/video_summaries_YYYYMMDD_HHMM.csv)
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
    prompt_file = "prompts/summarize_video.md"
    if not os.path.exists(prompt_file):
        print(f"Error: Prompt file '{prompt_file}' not found")
        return

    print("Loading prompt...")
    prompt = load_prompt(prompt_file)

    # Load transcripts
    print("Loading transcripts...")
    transcripts_df = load_transcripts(transcripts_file)
    if transcripts_df is None:
        return

    # Load video metadata from comments
    print("Loading video metadata...")
    metadata_df = load_comments()
    if metadata_df is None:
        return

    # Join transcripts with metadata
    df = transcripts_df.merge(metadata_df, on="video_id", how="left")

    # Check for missing metadata
    missing_metadata = df["video_title"].isna().sum()
    if missing_metadata > 0:
        print(f"Warning: {missing_metadata} videos have no metadata, skipping...")
        df = df.dropna(subset=["video_title"])

    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)

    # Generate default filename with timestamp if not provided
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        output_file = f"data/video_summaries_{timestamp}.csv"

    print(f"Processing {len(df)} videos...")

    # Generate summaries
    summaries = []
    for i, row in df.iterrows():
        video_id = row["video_id"]
        transcript = row["transcript"]

        # Prepare metadata dict
        video_metadata = {
            "video_title": row["video_title"],
            "video_channel": row["video_channel"],
            "video_published_at": row["video_published_at"],
            "video_description": row.get("video_description", ""),
        }

        print(f"[{i + 1}/{len(df)}] Summarizing video: {video_id}")

        summary_obj = summarize_video(client, prompt, video_metadata, transcript)

        if summary_obj:
            # Convert key_arguments list to JSON string for CSV storage
            import json

            summaries.append(
                {
                    "video_id": video_id,
                    "summary_text": summary_obj.summary_text,
                    "stance_congestion_pricing": summary_obj.stance_congestion_pricing,
                    "stance_confidence": summary_obj.stance_confidence,
                    "key_arguments": json.dumps(summary_obj.key_arguments),
                    "tone": summary_obj.tone,
                    "is_generated": row.get("is_generated", ""),
                    "language_code": row.get("language_code", ""),
                }
            )
            print(
                f"  → Summary: {len(summary_obj.summary_text)} chars, Stance: {summary_obj.stance_congestion_pricing}"
            )
        else:
            print(f"  → Failed to generate summary")

    # Save to CSV
    if summaries:
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "video_id",
                "summary_text",
                "stance_congestion_pricing",
                "stance_confidence",
                "key_arguments",
                "tone",
                "is_generated",
                "language_code",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(summaries)

        print(f"\n Successfully generated {len(summaries)} summaries")
        print(f" Saved to: {output_file}")
    else:
        print("No summaries generated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate video summaries from transcripts using OpenAI API"
    )
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        default=None,
        help="Input transcripts CSV file (default: latest file in data/)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output CSV filename (default: data/video_summaries_YYYYMMDD_HHMM.csv)",
    )

    args = parser.parse_args()
    summarize_videos(args.input, args.output)
