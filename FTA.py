import discord, asyncio, os, requests, time
from discord.ext import commands, tasks
from pymongo import MongoClient
import datetime
from matplotlib import pyplot as plt
from io import BytesIO


class FTA:
    def __init__(self):
        # Get Token
        with open(".token", "r", encoding="utf-8") as t:
            self.token = t.read().split()[0]
        print("Token_Key : ", self.token)

        # Get mongoDB cluster address
        with open(".mongodb", "r", encoding="utf-8") as t:
            self.cluster = t.read().split()[0]
        print("[mongoDB]", self.cluster)

        # Get API account
        with open(".account", "r", encoding="utf-8") as t:
            self.id = t.readline().strip("\n")
            self.pwd = t.readline()
        print("[API]{}/{}".format(self.id, self.pwd))

        # Bot Settings
        self.game = discord.Game("호드 척살")
        self.prefix = "?"
        self.db = MongoClient(self.cluster).get_database("wow_auction")


os.chdir(os.path.dirname(os.path.abspath(__file__)))
setup = FTA()
bot = commands.Bot(
    command_prefix=setup.prefix, status=discord.Status.online, activity=setup.game
)
item = setup.db["Item"]
live = setup.db["Live"]
wow_token = setup.db["Token"]

namespace = ""
locale = "ko_KR"
access_token = ""
params = {"namespace": namespace, "locale": locale, "access_token": access_token}
# Bot events


@bot.event
async def on_ready():
    print("We have logged in as {0.user}".format(bot))
    print("Guild List : {}".format(str(bot.guilds)))
    regenerate_access_token.start()
    refresh_live_data.start()
    update_wow_token_price.start()


@bot.event
async def on_guild_join(guild):
    print(
        "[{}]FTA joined at {} ({})".format(
            time.strftime("%c", time.localtime(time.time())), guild.name, guild.id
        )
    )
    try:
        await guild.system_channel.send(embed=discord.Embed(title="얼라이언스를 위하여!"))
    except discord.errors.Forbidden:
        print("(error code: 50013): Missing Permissions")
        await guild.leave()
        return


@bot.event
async def on_guild_remove(guild):
    print(
        "[{}]FTA removed at {} ({})".format(
            time.strftime("%c", time.localtime(time.time())), guild.name, guild.id
        )
    )


# Bot commands


@bot.command()
async def debug_leave_all_guilds(ctx):
    if ctx.author.id == 279204767472025600:
        for guild in bot.guilds:
            await guild.leave()


@bot.command()
async def 토큰(ctx):
    params["namespace"] = "dynamic-kr"
    response = requests.get(
        "https://kr.api.blizzard.com/data/wow/token/index", params
    ).json()

    data = [
        index["price"] for index in wow_token.find({}).sort("last_update_date_time", 1)
    ]
    plt.plot(data)
    plt.ylabel("price")
    plt.gca().axes.get_xaxis().set_visible(False)
    buffer = BytesIO()
    plt.savefig(buffer, format="png")
    buffer.seek(0)
    file = discord.File(buffer, filename="image.png")

    data = item.find_one({"name": "WoW 토큰"})
    params["namespace"] = "static-kr"
    response_image = requests.get(
        "https://kr.api.blizzard.com/data/wow/media/item/{}".format(data["_id"]),
        params,
    ).json()
    image_url = dict(response_image["assets"][0])["value"]

    embed = discord.Embed(title="WOW 토큰", colour=discord.Colour.blue())
    embed.add_field(name="가격", value=int(response["price"] / 10000))
    embed.add_field(
        name="last_update_date_time",
        value=datetime.datetime.fromtimestamp(
            response["last_updated_timestamp"] / 1000
        ),
        inline=False,
    )
    embed.set_thumbnail(url=image_url)
    embed.set_image(url="attachment://image.png")
    await ctx.send(file=file, embed=embed)


@bot.command()
async def 임베드(ctx):
    params["namespace"] = "static-kr"
    response = requests.get(
        "https://kr.api.blizzard.com/data/wow/media/item/{}".format("171833"), params
    ).json()
    image_url = dict(response["assets"][0])["value"]

    embed = discord.Embed(title="마력 깃든 암영 비단", colour=discord.Colour.blue())
    embed.set_footer(text="경매장 가격은 1시간마다 새로고침 됩니다.")
    embed.set_thumbnail(url=image_url)
    embed.add_field(
        name="가격:",
        value="230:yellow_circle: 10:white_circle: 0:brown_circle:",
        inline=False,
    )

    await ctx.send(embed=embed)


@bot.command()
async def 검색(ctx, *args, page=1):
    params["namespace"] = "dynamic-kr"
    if args[-1].isdigit():
        page = int(args[-1])
        args = args[:-1]
    name = " ".join(args)

    data = item.find_one({"name": name})
    if data is not None:
        items = live.find({"item.id": data["_id"]})
        value = None
        type_item = None

        for tmp in items:
            if value is None:
                try:
                    tmp["buyout"]
                    type_item = "buyout"
                except KeyError:
                    type_item = "unit_price"
                value = tmp[type_item]
            else:
                value = tmp[type_item] if value > tmp[type_item] else value

        if value is None:
            await ctx.send(
                embed=discord.Embed(
                    title="경매장에 해당 매물이 없습니다.", colour=discord.Colour.blue()
                )
            )
            return
        out = [int(value % 100), int(value / 100 % 100), int(value / 10000)]

        params["namespace"] = "static-kr"
        response = requests.get(
            "https://kr.api.blizzard.com/data/wow/media/item/{}".format(data["_id"]),
            params,
        ).json()
        image_url = dict(response["assets"][0])["value"]

        embed = discord.Embed(title=name, colour=discord.Colour.blue())
        embed.set_footer(text="경매장 가격은 1시간마다 새로고침 됩니다.")
        embed.set_thumbnail(url=image_url)
        embed.add_field(
            name="{}:".format("가격" if type_item == "unit_price" else "즉시 구입가"),
            value="{}:yellow_circle: {}:white_circle: {}:brown_circle:".format(
                out[2], out[1], out[0]
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    else:
        response = item.find({"name": {"$regex": name}}).skip((page - 1) * 10).limit(10)
        if response is None:
            await ctx.send(embed=discord.Embed(title="fail"))
        else:
            out = ""
            i = 0
            for index in response:
                out += index["name"] + "\n"
                i += 1
                if i > 10:
                    break
            embed = discord.Embed(
                title="이걸 찾으셨나요?", description=out, colour=discord.Colour.blue()
            )
            embed.set_footer(text="?검색 이름 (페이지) \t\t\t[{}페이지]".format(page))
            await ctx.send(embed=embed)


@tasks.loop(hours=12.0)
async def regenerate_access_token():
    data = {"grant_type": "client_credentials"}
    response = requests.post(
        "https://us.battle.net/oauth/token", data=data, auth=(setup.id, setup.pwd)
    )
    access_token = response.json()["access_token"]
    params["access_token"] = response.json()["access_token"]
    print(
        "[{}]access_token was regenerated : {}".format(
            time.strftime("%c", time.localtime(time.time())), access_token
        )
    )


@tasks.loop(hours=1.0)
async def refresh_live_data():
    params["namespace"] = "dynamic-kr"
    live.drop()
    auction_req = requests.get(
        "https://kr.api.blizzard.com/data/wow/connected-realm/2116/auctions", params
    )
    live.insert_many(auction_req.json()["auctions"])
    print(
        "[{}]auction_live_data has refreshed".format(
            time.strftime("%c", time.localtime(time.time()))
        )
    )


@tasks.loop(minutes=20.0)
async def update_wow_token_price():
    params["namespace"] = "dynamic-kr"
    response = requests.get(
        "https://kr.api.blizzard.com/data/wow/token/index", params
    ).json()

    if not wow_token.count_documents(
        {"last_update_date_time": response["last_updated_timestamp"]}
    ):
        wow_token.insert_one(
            {
                "last_update_date_time": response["last_updated_timestamp"],
                "price": int(response["price"] / 10000),
            }
        )
        print(
            "[{}]WOW Token price was updated : {}".format(
                time.strftime("%c", time.localtime(time.time())),
                int(response["price"] / 10000),
            )
        )

    if wow_token.count_documents({}) > 504:
        wow_token.find_one_and_delete({}, sort=[("last_update_date_time", 1)])


bot.run(setup.token)