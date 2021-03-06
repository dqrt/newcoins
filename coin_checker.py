import asyncio
from collections import namedtuple
from logging import getLogger

from aiohttp import ClientSession
from aiotg import Bot, logging

import db
import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(settings.BOT_NAME)

Coin = namedtuple('Coin', ['id', 'symbol', 'name'])


class CoinChecker:
    bot = Bot(settings.BOT_TOKEN)
    channel = bot.channel(settings.CHANNEL_ID)
    url = 'https://api.coinmarketcap.com/v1/ticker?limit=0'

    async def check(self):
        api_coins = await self.api_coins()
        api_ids = set(c.id for c in api_coins)
        db_ids = await db.get_coins()
        if not db_ids:
            # initial launch, don't send message to channel, only put coins to db
            await db.add_coins(api_ids)
            getLogger().info(f'Initial launch, {len(api_ids)} ids added.')
            return
        new_coin_ids = api_ids - db_ids
        if not new_coin_ids:
            getLogger().info('There is no new coins :(')
            return
        for coin_id in new_coin_ids:
            coin_info = self.coin_info_by_id(api_coins, coin_id)
            getLogger().info(f'New coin: {coin_info}')
            message = self.compose_message(coin_info)
            await self.send_message(message)
        await db.add_coins(new_coin_ids)

    async def periodic(self, interval=None):
        while True:
            getLogger().info('sleeping')
            await asyncio.sleep(interval or settings.CHECK_INTERVAL)
            await self.check()

    async def send_message(self, coin_info):
        await self.channel.send_text(coin_info, parse_mode='Markdown')

    async def api_coins(self):
        async with ClientSession() as s:
            response = await s.get(self.url)
            resp_json = await response.json()
            return set(
                Coin(
                    c['id'],
                    c['symbol'],
                    c['name'],
                ) for c in resp_json
            )

    @staticmethod
    def coin_info_by_id(api_coins, coin_id):
        for c in api_coins:
            if c.id == coin_id:
                return c

    @staticmethod
    def compose_message(coin_info):
        return (
            f'[{coin_info.name} ({coin_info.symbol})]'
            f'(https://coinmarketcap.com/currencies/{coin_info.id}/)'
        )


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.init_db())
    try:
        logger.info('bot started')
        checker = CoinChecker()
        loop.run_until_complete(checker.check())
        asyncio.ensure_future(checker.periodic(), loop=loop)
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info('bot stopped')
