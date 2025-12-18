#!/usr/bin/env python3
"""
Clear Redis streams to remove stale messages.

Use this script when:
1. Upgrading from Base64 SSR to Full CSR
2. Old messages in Redis are causing errors
3. You want to start fresh without old data

WARNING: This will delete all messages in video-frames and processed-frames streams!
"""

import redis
import os

# Redis Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))

def clear_streams():
    """Clear all messages from Redis streams"""
    try:
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=False
        )
        
        # Test connection
        client.ping()
        print(f"✓ Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        
        # Get stream lengths before clearing
        input_len = client.xlen('video-frames')
        output_len = client.xlen('processed-frames')
        
        print(f"\n📊 Current stream lengths:")
        print(f"   video-frames: {input_len} messages")
        print(f"   processed-frames: {output_len} messages")
        
        if input_len == 0 and output_len == 0:
            print("\n✓ Streams are already empty. Nothing to clear.")
            return
        
        # Confirm before clearing
        print(f"\n⚠️  WARNING: This will delete ALL messages from both streams!")
        confirm = input("Type 'YES' to confirm: ")
        
        if confirm != 'YES':
            print("❌ Cancelled. No data was deleted.")
            return
        
        # Clear streams by deleting and recreating
        print("\n🗑️  Clearing streams...")
        
        # Delete streams
        if input_len > 0:
            client.delete('video-frames')
            print("   ✓ Deleted 'video-frames' stream")
        
        if output_len > 0:
            client.delete('processed-frames')
            print("   ✓ Deleted 'processed-frames' stream")
        
        # Recreate consumer group
        try:
            client.xgroup_create(
                'video-frames',
                'processor-group',
                id='0',
                mkstream=True
            )
            print("   ✓ Recreated consumer group 'processor-group'")
        except redis.exceptions.ResponseError as e:
            if 'BUSYGROUP' in str(e):
                print("   ℹ️  Consumer group already exists")
        
        # Verify
        input_len_after = client.xlen('video-frames')
        output_len_after = client.xlen('processed-frames')
        
        print(f"\n✅ Streams cleared successfully!")
        print(f"   video-frames: {input_len} → {input_len_after}")
        print(f"   processed-frames: {output_len} → {output_len_after}")
        
    except redis.exceptions.ConnectionError:
        print(f"❌ Could not connect to Redis at {REDIS_HOST}:{REDIS_PORT}")
        print("   Make sure Redis is running.")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == '__main__':
    print("🧹 Redis Streams Cleaner")
    print("=" * 50)
    clear_streams()
