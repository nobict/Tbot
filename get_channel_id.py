from pyrogram import Client
import asyncio
from dotenv import load_dotenv
import os

load_dotenv()

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")

async def main():
    print("Starting client...")
    
    # Get phone number
    while True:
        phone = input("\nEnter your phone number (including country code, e.g., +1234567890): ")
        if phone.startswith('+') and phone[1:].isdigit():
            break
        print("Invalid format! Please include country code with + symbol")
    
    # Create client with phone number
    client = Client(
        "user_account",
        api_id=api_id,
        api_hash=api_hash,
        phone_number=phone
    )
    
    async with client as app:
        try:
            # Try to get channel directly from the invite link
            invite_link = "https://t.me/+PKfGhwMWccA4MDli"
            hash_part = invite_link.split('+')[1]
            
            try:
                # Try to get chat info directly
                chat = await app.get_chat(f"https://t.me/+{hash_part}")
                print(f"\n✅ Found channel: {chat.title}")
                print(f"Channel ID: {chat.id}")
                print(f"\nAdd this to your .env file:")
                print(f"CHANNEL_ID={chat.id}")
                return
            except Exception as e:
                print(f"\nCouldn't get chat directly: {str(e)}")
            
            # If direct access fails, try listing all dialogs
            print("\nTrying to list all chats...")
            async for dialog in app.get_dialogs():
                print(f"\nChecking chat: {dialog.chat.title}")
                print(f"Chat type: {dialog.chat.type}")
                print(f"Chat ID: {dialog.chat.id}")
                
                if dialog.chat.type in ["channel", "supergroup"]:
                    response = input("\nIs this the correct channel? (y/n): ").lower()
                    if response == 'y':
                        print(f"\nAdd this to your .env file:")
                        print(f"CHANNEL_ID={dialog.chat.id}")
                        return
            
            print("\nChannel not found in your dialogs.")
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())