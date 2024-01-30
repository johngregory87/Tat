# Copyright 2023, Nathan Harris.
# All rights reserved.
# Tauticord is released as-is under the "GNU General Public License".
# Please see the LICENSE file that should have been included as part of this package.
import argparse

import modules.discord_connector as discord
import modules.logs as logging
import modules.tautulli_connector as tautulli
from consts import (
    GOOGLE_ANALYTICS_ID,
    APP_NAME,
    DEFAULT_CONFIG_PATH,
    DEFAULT_LOG_DIR,
    CONSOLE_LOG_LEVEL,
    FILE_LOG_LEVEL,
)
from modules.analytics import GoogleAnalytics
from modules.config_parser import Config
from modules.statics import splash_logo
from modules.errors import determine_exit_code

# Parse arguments
parser = argparse.ArgumentParser(description="Tauticord - Discord bot for Tautulli")

"""
Bot will use config, in order:
1. Explicit config file path provided as CLI argument, if included, or
2. Default config file path, if exists, or
3. Environmental variables
"""
parser.add_argument("-c", "--config", help="Path to config file", default=DEFAULT_CONFIG_PATH)
parser.add_argument("-l", "--log", help="Log file directory", default=DEFAULT_LOG_DIR)

args = parser.parse_args()

# Set up logging
logging.init(app_name=APP_NAME, console_log_level=CONSOLE_LOG_LEVEL, log_to_file=True, log_file_dir=args.log,
             file_log_level=FILE_LOG_LEVEL)

# Set up configuration
config = Config(app_name=APP_NAME, config_path=f"{args.config}")

# Set up analytics
analytics = GoogleAnalytics(analytics_id=GOOGLE_ANALYTICS_ID,
                            anonymous_ip=True,
                            do_not_track=not config.extras.allow_analytics)

if __name__ == '__main__':
    logging.info(splash_logo())
    logging.info("Starting Tauticord...")

    # Used by GitHub Actions to stop the bot from running during tests
    if config.extras._docker_kill_switch:
        logging.info("Docker kill switch is enabled. Exiting...")
        exit(201)

    # noinspection PyBroadException
    try:
        tautulli_connector = tautulli.TautulliConnector(
            base_url=config.tautulli.url,
            api_key=config.tautulli.api_key,
            terminate_message=config.tautulli.terminate_message,
            analytics=analytics,
            time_manager=config.tautulli.time_manager,
            server_name=config.tautulli.server_name,
            text_manager=config.tautulli.text_manager,
            disable_ssl_verification=config.tautulli.disable_ssl_verification,
        )

        discord_connector = discord.DiscordConnector(
            token=config.discord.bot_token,
            guild_id=config.discord.server_id,
            admin_ids=config.discord.admin_ids,
            refresh_time=config.tautulli.refresh_interval,
            library_refresh_time=config.tautulli.library_refresh_interval,
            tautulli_use_summary_message=config.discord.use_summary_text_message,
            tautulli_channel_name=config.discord.channel_name,
            tautulli_connector=tautulli_connector,
            voice_channel_settings=config.tautulli.voice_channel_settings,
            display_live_stats=config.tautulli.any_live_stats_channels_enabled,
            display_library_stats=config.tautulli.any_library_stats_channels_enabled,
            thousands_separator=config.tautulli.thousands_separator,
            nitro=config.discord.has_discord_nitro,
            performance_monitoring=config.performance,
            analytics=analytics,
        )

        discord_connector.connect()
    except Exception as e:
        logging.fatal(f"Fatal error occurred. Shutting down: {e}")
        exit_code = determine_exit_code(exception=e)
        logging.fatal(f"Exiting with code {exit_code}")
        exit(exit_code)  # Exit the script if an error bubbles up (like an internet connection error)
