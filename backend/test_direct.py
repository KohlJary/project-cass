#!/usr/bin/env python3
"""Test Wonderland tools directly as if called from HTTP endpoint"""
import asyncio
import sys
from handlers.wonderland import execute_wonderland_tool
from memory import CassMemory

async def test():
    memory = CassMemory()
    daemon_id = "cass"
    
    print(f"Testing with daemon_id: {daemon_id}")
    print("=" * 60)
    
    # Test describe_my_home
    result = await execute_wonderland_tool(
        tool_name="describe_my_home",
        tool_input={},
        daemon_id=daemon_id,
        memory=memory
    )
    print("\ndescribe_my_home result:")
    print(f"Success: {result.get('success')}")
    if result.get('success'):
        import json
        data = json.loads(result['result'])
        print(f"Has home: {data.get('has_home')}")
        if data.get('has_home'):
            print(f"Room name: {data.get('room_name')}")
            print(f"Room ID: {data.get('room_id')}")
    else:
        print(f"Error: {result.get('error')}")
    
    print("\n" + "=" * 60)
    
    # Test get_wonderland_status
    result = await execute_wonderland_tool(
        tool_name="get_wonderland_status",
        tool_input={},
        daemon_id=daemon_id,
        memory=None  # This tool doesn't use memory
    )
    print("\nget_wonderland_status result:")
    print(f"Success: {result.get('success')}")
    if result.get('success'):
        import json
        data = json.loads(result['result'])
        print(f"Registered: {data.get('registered')}")
        if data.get('registered'):
            print(f"Has home: {data.get('has_home')}")
            if data.get('home'):
                print(f"Home: {data.get('home')}")
            print(f"Trust level: {data.get('trust_level')}")
    else:
        print(f"Error: {result.get('error')}")

if __name__ == "__main__":
    asyncio.run(test())
