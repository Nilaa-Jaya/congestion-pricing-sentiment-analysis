#!/usr/bin/env python3
"""
YouTube Comment Scraper
Scrapes comments from YouTube videos using the YouTube Data API v3
"""

import os
import csv
import argparse
from datetime import datetime
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pandas as pd

# Load environment variables
load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")


def search_videos(youtube, query, max_results=10):
    """
    Search for videos matching the given query.

    Args:
            youtube: YouTube API service object
            query: Search query string
            max_results: Maximum number of videos to return (default: 10)

    Returns:
            List of video dictionaries with id, title, and channel info
    """
    try:
        request = youtube.search().list(
            part="snippet",
            q=query,
            type="video",
            maxResults=max_results,
            order="relevance",
        )
        response = request.execute()

        videos = []
        for item in response.get("items", []):
            video = {
                "video_id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
                "published_at": item["snippet"]["publishedAt"],
            }
            videos.append(video)

        return videos

    except HttpError as e:
        print(f"An HTTP error occurred: {e}")
        return []


def get_video_comments(youtube, video_id):
    """
    Fetch all comments for a given video, handling pagination.

    Args:
            youtube: YouTube API service object
            video_id: YouTube video ID

    Returns:
            List of comment dictionaries
    """
    comments = []

    try:
        request = youtube.commentThreads().list(
            part="snippet", videoId=video_id, maxResults=100, textFormat="plainText"
        )

        while request:
            response = request.execute()

            for item in response.get("items", []):
                comment = item["snippet"]["topLevelComment"]["snippet"]
                comments.append(
                    {
                        "video_id": video_id,
                        "author": comment["authorDisplayName"],
                        "comment_text": comment["textDisplay"],
                        "like_count": comment["likeCount"],
                        "published_at": comment["publishedAt"],
                    }
                )

            # Get next page of comments
            request = youtube.commentThreads().list_next(request, response)

        return comments

    except HttpError as e:
        if "commentsDisabled" in str(e):
            print(f"Comments disabled for video: {video_id}")
        else:
            print(f"An HTTP error occurred for video {video_id}: {e}")
        return []


def load_comments(csv_file="comments.csv"):
    """
    Load comments from CSV into a pandas DataFrame.

    Args:
            csv_file: Path to the CSV file (default: comments.csv)

    Returns:
            pandas DataFrame with parsed dates and types
    """
    try:
        df = pd.read_csv(csv_file)

        # Convert published_at to datetime
        df["published_at"] = pd.to_datetime(df["published_at"])

        # Ensure like_count is integer
        df["like_count"] = df["like_count"].astype(int)

        return df

    except FileNotFoundError:
        print(f"Error: File '{csv_file}' not found")
        return None
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return None


def scrape_comments(query, max_videos=10, output_file="comments.csv"):
    """
    Main orchestrator function to search videos and scrape comments.

    Args:
            query: Search query string
            max_videos: Maximum number of videos to process
            output_file: Output CSV filename
    """
    if not API_KEY or API_KEY == "your_api_key_here":
        print("Error: Please set your YouTube API key in the .env file")
        return

    # Build YouTube API service
    youtube = build("youtube", "v3", developerKey=API_KEY)

    print(f"Searching for videos matching: '{query}'...")
    videos = search_videos(youtube, query, max_videos)

    if not videos:
        print("No videos found.")
        return

    print(f"Found {len(videos)} videos. Fetching comments...")

    all_comments = []
    for i, video in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}] Processing: {video['title']}")
        comments = get_video_comments(youtube, video["video_id"])

        # Add video metadata to each comment
        for comment in comments:
            comment["video_title"] = video["title"]
            comment["video_channel"] = video["channel"]

        all_comments.extend(comments)
        print(f"Collected {len(comments)} comments")

    # Export to CSV
    if all_comments:
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "video_id",
                "video_title",
                "video_channel",
                "author",
                "comment_text",
                "like_count",
                "published_at",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_comments)

        print(
            f"\n Successfully scraped {len(all_comments)} comments from {len(videos)} videos"
        )
        print(f" Saved to: {output_file}")
    else:
        print("No comments collected.")


def main():
    parser = argparse.ArgumentParser(
        description="Scrape YouTube comments for videos matching a search query"
    )
    parser.add_argument(
        "-q",
        "--query",
        type=str,
        default="NYC congestion pricing",
        help='Search query (default: "NYC congestion pricing")',
    )
    parser.add_argument(
        "-n",
        "--max-videos",
        type=int,
        default=10,
        help="Maximum number of videos to process (default: 10)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="comments.csv",
        help="Output CSV filename (default: comments.csv)",
    )
    parser.add_argument(
        "-a",
        "--analyze",
        type=str,
        metavar="FILE",
        help="Load and display basic stats from existing CSV file",
    )

    args = parser.parse_args()

    if args.analyze:
        df = load_comments(args.analyze)
        if df is not None:
            print(f"\n=== Analysis of {args.analyze} ===\n")
            print(f"Total comments: {len(df)}")
            print(f"Unique videos: {df['video_id'].nunique()}")
            print(f"Unique authors: {df['author'].nunique()}")
            print(
                f"Date range: {df['published_at'].min()} to {df['published_at'].max()}"
            )
            print("\nTop 5 authors by comment count:")
            print(df["author"].value_counts().head())
            print("\nTop 5 most liked comments:")
            print(
                df.nlargest(5, "like_count")[["author", "like_count", "comment_text"]]
            )
    else:
        scrape_comments(args.query, args.max_videos, args.output)


if __name__ == "__main__":
    main()
