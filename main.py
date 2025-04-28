import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))
from helpers.custom_logger import CustomLogger

import asyncio
from dotenv import load_dotenv
load_dotenv()

from services.server_connection import ServerConnection

if __name__ == '__main__':
    CustomLogger()._get_logger().info("App: __main__")

    # Get uid from command line
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--uid', type=str, required=True, help='User ID')
    args = parser.parse_args()
    
    asyncio.run(ServerConnection(uid=args.uid)._instance._connect_to_server())