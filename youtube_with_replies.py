#!/usr/bin/env python3
"""
YouTube Comment Scraper
Scrapes comments and their replies from YouTube videos using the YouTube Data API v3
"""

import os
import csv
import argparse
import re
from datetime import datetime
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pandas as pd
import time

# Load environment variables
load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")


def parse_duration(duration):
    """
    Convert ISO 8601 duration (e.g., PT2M18S) to seconds.

    Args:
            duration: ISO 8601 duration string

    Returns:
            Total duration in seconds as integer
    """
    if not duration:
        return 0

    # Pattern matches PT1H30M5S format
    pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
    match = re.match(pattern, duration)

    if not match:
        return 0

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    return hours * 3600 + minutes * 60 + seconds


def get_video_details(youtube, video_ids):
    """
    Fetch detailed metadata for a list of video IDs.

    Args:
            youtube: YouTube API service object
            video_ids: List of video IDs

    Returns:
            Dictionary mapping video_id to metadata dict
    """
    if not video_ids:
        return {}

    try:
        request = youtube.videos().list(
            part="snippet,statistics,contentDetails", id=",".join(video_ids)
        )
        response = request.execute()

        video_details = {}
        for item in response.get("items", []):
            video_id = item["id"]
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})

            video_details[video_id] = {
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
                "duration": parse_duration(content.get("duration", "")),
                "description": item["snippet"].get("description", ""),
            }

        return video_details

    except HttpError as e:
        print(f"An HTTP error occurred fetching video details: {e}")
        return {}


def search_videos(youtube, query, max_results=50):
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
        video_ids = []
        for rank, item in enumerate(response.get("items", []), start=1):
            video_id = item["id"]["videoId"]
            video_ids.append(video_id)
            video = {
                "video_id": video_id,
                "relevance_rank": rank,
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
                "video_published_at": item["snippet"]["publishedAt"],
            }
            videos.append(video)

        # Enrich with detailed metadata
        details = get_video_details(youtube, video_ids)
        for video in videos:
            vid_id = video["video_id"]
            if vid_id in details:
                video.update(details[vid_id])

        return videos

    except HttpError as e:
        print(f"An HTTP error occurred: {e}")
        return []


def get_video_comments(youtube, video_id):
    """
    Fetch all comments and their replies for a given video, handling pagination.

    Args:
            youtube: YouTube API service object
            video_id: YouTube video ID

    Returns:
            List of comment dictionaries including replies
    """
    comments = []
    comment_count = 0
    reply_count = 0

    try:
        # Request top-level comments with replies
        request = youtube.commentThreads().list(
            part="snippet,replies",
            videoId=video_id,
            maxResults=100,
            textFormat="plainText"
        )

        while request:
            response = request.execute()

            for item in response.get("items", []):
                # Process the top-level comment
                top_comment = item["snippet"]["topLevelComment"]["snippet"]
                comment_id = item["id"]  # Thread ID for the top-level comment
                
                comment_data = {
                    "video_id": video_id,
                    "comment_id": comment_id,
                    "parent_id": None,  # Top-level comments have no parent
                    "is_reply": False,
                    "author": top_comment["authorDisplayName"],
                    "comment_text": top_comment["textDisplay"],
                    "comment_like_count": top_comment["likeCount"],
                    "comment_published_at": top_comment["publishedAt"],
                }
                comments.append(comment_data)
                comment_count += 1
                
                # Process replies if they exist
                if "replies" in item:
                    for reply in item["replies"].get("comments", []):
                        reply_snippet = reply["snippet"]
                        reply_data = {
                            "video_id": video_id,
                            "comment_id": reply["id"],
                            "parent_id": comment_id,  # Link to parent comment
                            "is_reply": True,
                            "author": reply_snippet["authorDisplayName"],
                            "comment_text": reply_snippet["textDisplay"],
                            "comment_like_count": reply_snippet["likeCount"],
                            "comment_published_at": reply_snippet["publishedAt"],
                        }
                        comments.append(reply_data)
                        reply_count += 1
                
                # Check if there are more replies that need to be fetched separately
                total_reply_count = item["snippet"].get("totalReplyCount", 0)
                fetched_replies = len(item.get("replies", {}).get("comments", []))
                
                if total_reply_count > fetched_replies:
                    try:
                        # Fetch all remaining replies for this comment thread
                        replies_request = youtube.comments().list(
                            part="snippet",
                            parentId=comment_id,
                            maxResults=100,
                            textFormat="plainText"
                        )
                        
                        while replies_request:
                            # Add a small delay to avoid rate limits
                            time.sleep(0.2)
                            
                            replies_response = replies_request.execute()
                            
                            for reply in replies_response.get("items", []):
                                # Skip replies we already have
                                reply_id = reply["id"]
                                if any(c["comment_id"] == reply_id for c in comments):
                                    continue
                                    
                                reply_snippet = reply["snippet"]
                                reply_data = {
                                    "video_id": video_id,
                                    "comment_id": reply_id,
                                    "parent_id": comment_id,  # Link to parent comment
                                    "is_reply": True,
                                    "author": reply_snippet["authorDisplayName"],
                                    "comment_text": reply_snippet["textDisplay"],
                                    "comment_like_count": reply_snippet["likeCount"],
                                    "comment_published_at": reply_snippet["publishedAt"],
                                }
                                comments.append(reply_data)
                                reply_count += 1
                            
                            # Get the next page of replies
                            replies_request = youtube.comments().list_next(replies_request, replies_response)
                    except HttpError as e:
                        print(f"  Error fetching replies for comment {comment_id}: {e}")
                        # Continue with other comments even if one fails

            # Get next page of top-level comments
            request = youtube.commentThreads().list_next(request, response)
            
            # Add a small delay between page requests to avoid hitting rate limits
            if request:
                time.sleep(0.5)

        print(f"  → Collected {comment_count} comments and {reply_count} replies")
        return comments

    except HttpError as e:
        if "commentsDisabled" in str(e):
            print(f"Comments disabled for video: {video_id}")
        else:
            print(f"An HTTP error occurred for video {video_id}: {e}")
        return []


def load_comments(csv_file=None):
    """
    Load comments from CSV into a pandas DataFrame.

    Args:
            csv_file: Path to the CSV file (default: latest file in data/)

    Returns:
            pandas DataFrame with parsed dates and types
    """
    try:
        # If no file specified, find the latest CSV in data/
        if csv_file is None:
            import glob
            csv_files = glob.glob("data/youtube_comments_*.csv")
            if not csv_files:
                print("Error: No CSV files found in data/ directory")
                return None
            csv_file = max(csv_files, key=os.path.getmtime)
            print(f"Loading latest file: {csv_file}")

        df = pd.read_csv(csv_file)

        # Convert date columns to datetime
        if "video_published_at" in df.columns:
            df["video_published_at"] = pd.to_datetime(df["video_published_at"])
        if "comment_published_at" in df.columns:
            df["comment_published_at"] = pd.to_datetime(df["comment_published_at"])

        # Convert numeric columns to integers
        numeric_cols = [
            "relevance_rank",
            "video_view_count",
            "video_like_count",
            "video_comment_count",
            "video_duration",
            "comment_like_count",
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].astype(int)

        return df

    except FileNotFoundError:
        print(f"Error: File '{csv_file}' not found")
        return None
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return None


def scrape_comments(query, max_videos=50, output_file=None):
    """
    Main orchestrator function to search videos and scrape comments with replies.

    Args:
            query: Search query string
            max_videos: Maximum number of videos to process
            output_file: Output CSV filename (default: data/youtube_comments_YYYYMMDD_HHMM.csv)
    """
    if not API_KEY or API_KEY == "your_api_key_here":
        print("Error: Please set your YouTube API key in the .env file")
        return

    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)

    # Generate default filename with timestamp if not provided
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        output_file = f"data/youtube_comments_{timestamp}.csv"

    # Build YouTube API service
    youtube = build("youtube", "v3", developerKey=API_KEY)

    print(f"Searching for videos matching: '{query}'...")
    videos = search_videos(youtube, query, max_videos)

    if not videos:
        print("No videos found.")
        return

    print(f"Found {len(videos)} videos. Fetching comments and replies...")

    all_comments = []
    total_top_comments = 0
    total_replies = 0
    
    for i, video in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}] Processing: {video['title']}")
        
        # Get comments and replies
        comments = get_video_comments(youtube, video["video_id"])
        
        # Count top comments and replies
        top_comments = sum(1 for c in comments if not c.get("is_reply", False))
        replies = sum(1 for c in comments if c.get("is_reply", False))
        total_top_comments += top_comments
        total_replies += replies
        
        # Add video metadata to each comment
        for comment in comments:
            comment["relevance_rank"] = video.get("relevance_rank", 0)
            comment["video_title"] = video["title"]
            comment["video_channel"] = video["channel"]
            comment["video_published_at"] = video.get("video_published_at", "")
            comment["video_view_count"] = video.get("view_count", 0)
            comment["video_like_count"] = video.get("like_count", 0)
            comment["video_comment_count"] = video.get("comment_count", 0)
            comment["video_duration"] = video.get("duration", 0)
            comment["video_description"] = video.get("description", "")

        all_comments.extend(comments)
        print(f"  → Collected {len(comments)} items ({top_comments} comments, {replies} replies)")
        
        # Add a delay between videos to avoid hitting rate limits
        if i < len(videos):
            time.sleep(1)

    # Export to CSV
    if all_comments:
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "video_id",
                "comment_id",
                "parent_id",
                "is_reply",
                "relevance_rank",
                "video_title",
                "video_channel",
                "video_published_at",
                "video_view_count",
                "video_like_count",
                "video_comment_count",
                "video_duration",
                "video_description",
                "author",
                "comment_text",
                "comment_like_count",
                "comment_published_at",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_comments)

        print(
            f"\nSuccessfully scraped {total_top_comments} comments and {total_replies} replies"
        )
        print(f"Total items: {len(all_comments)}")
        print(f"Saved to: {output_file}")
    else:
        print("No comments collected.")


def analyze_comments_csv(file_path):
    """Analyze a comments CSV file with hierarchical data."""
    
    df = pd.read_csv(file_path)
    
    # Basic stats
    total_comments = len(df)
    top_level_comments = df[df["is_reply"] == False].shape[0]
    replies = df[df["is_reply"] == True].shape[0]
    unique_videos = df["video_id"].nunique()
    unique_authors = df["author"].nunique()
    
    # Comments with most replies
    if "parent_id" in df.columns:
        reply_counts = df[df["is_reply"] == True]["parent_id"].value_counts()
        top_parents = reply_counts.head(10).reset_index()
        top_parents.columns = ["comment_id", "reply_count"]
        
        # Get the text of these top comments
        if top_parents.shape[0] > 0:
            top_parent_comments = df[df["comment_id"].isin(top_parents["comment_id"])]
            
    print("\n=== Analysis of Comments Data ===\n")
    print(f"Total items: {total_comments}")
    print(f"Top-level comments: {top_level_comments}")
    print(f"Replies: {replies}")
    print(f"Unique videos: {unique_videos}")
    print(f"Unique authors: {unique_authors}")
    
    if "parent_id" in df.columns and replies > 0:
        print("\nTop 5 comments with most replies:")
        for _, row in top_parents.head(5).iterrows():
            comment_text = df[df["comment_id"] == row["comment_id"]]["comment_text"].values[0]
            if len(comment_text) > 50:
                comment_text = comment_text[:50] + "..."
            print(f"  - {comment_text} ({row['reply_count']} replies)")
    
    # Videos with most engagement
    video_stats = df.groupby("video_id").agg(
        comments=("comment_id", "count"),
        top_level=("is_reply", lambda x: (~x).sum()),
        replies=("is_reply", sum)
    ).sort_values("comments", ascending=False)
    
    print("\nTop 5 videos by comment count:")
    for i, (vid, row) in enumerate(video_stats.head(5).iterrows(), 1):
        title = df[df["video_id"] == vid]["video_title"].iloc[0]
        print(f"  {i}. {title[:50]}... - {row['comments']} items ({row['top_level']} comments, {row['replies']} replies)")


def main():
    parser = argparse.ArgumentParser(
        description="Scrape YouTube comments and replies for videos matching a search query"
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
        default=50,
        help="Maximum number of videos to process (default: 50)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output CSV filename (default: data/youtube_comments_YYYYMMDD_HHMM.csv)",
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
        analyze_comments_csv(args.analyze)
    else:
        scrape_comments(args.query, args.max_videos, args.output)


if __name__ == "__main__":
    main()
