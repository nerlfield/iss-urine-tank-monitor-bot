# ISS Urine Tank Monitor Bot

This bot monitors the International Space Station (ISS) urine tank levels in real-time using NASA's official data feed provided through Lightstreamer.

## About Lightstreamer and ISS Data

Lightstreamer (push.lightstreamer.com) is the official real-time data streaming service used by NASA to distribute telemetry data from the International Space Station. The service provides live updates of various ISS systems and parameters, including the urine tank levels tracked by this bot.

The data comes from NASA's "ISSLIVE" feed, specifically monitoring the NODE3000005 parameter which represents the ISS urine tank level. This is the same data feed used by NASA's own mission control interfaces.

The bot connects to this official data source using the Lightstreamer client library and provides Telegram users with real-time notifications when the urine tank level changes significantly.

## Data Reliability

Since this bot uses NASA's official telemetry feed, the data is as reliable as what NASA mission control sees. The connection is made directly to push.lightstreamer.com using the public "ISSLIVE" data adapter, ensuring we get authentic ISS telemetry data.

You can verify the bot's connection status and current readings using the /test and /status commands.

# Running the Project

1. Create a `.env` file and add the variable: `TELEGRAM_TOKEN=<your_bot_token_here>`
2. Install Docker following the official documentation: https://docs.docker.com/engine/install/
3. Run `docker compose up --build -d` to start the project