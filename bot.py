import discord
from discord import app_commands
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import logging
from logging.handlers import TimedRotatingFileHandler
import json
from timetable_functions import get_timetable, get_activities
from request_AI import gpt_35_api
from qr_code import generate_qr_code
import io
from weather import *


# Set up general bot logging
log_file = os.path.join(os.getcwd(), 'bot_logs.log')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
file_handler = TimedRotatingFileHandler(log_file, when='midnight', interval=1, backupCount=30, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
file_handler.suffix = "%Y-%m-%d"
logger.addHandler(file_handler)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

# Set up QR code specific logging
qrcode_log_file = os.path.join(os.getcwd(), 'qrcode_logs.log')
qrcode_logger = logging.getLogger('qrcode')
qrcode_logger.setLevel(logging.INFO)
qrcode_file_handler = TimedRotatingFileHandler(qrcode_log_file, when='midnight', interval=1, backupCount=30, encoding='utf-8')
qrcode_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
qrcode_file_handler.suffix = "%Y-%m-%d"
qrcode_logger.addHandler(qrcode_file_handler)

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Initialize bot with intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# Developer user ID
DEV_USER_ID = "931848512633700384"

def get_available_classes():
    """Load available classes from timetale.json."""
    try:
        file_path = os.path.join('test_data', 'timetale.json')
        resolved_path = os.path.abspath(file_path)
        logger.info(f"Loading classes from: {resolved_path}")
        with open(file_path, 'r', encoding='utf-8') as file:
            timetable_data = json.load(file)
        classes = list(timetable_data.keys())
        if not classes:
            logger.error("No classes found in timetale.json")
            return None
        return classes[:25]
    except FileNotFoundError:
        logger.error(f"timetale.json not found at {resolved_path}")
        return None
    except json.JSONDecodeError:
        logger.error("Invalid JSON in timetale.json")
        return None
    except Exception as e:
        logger.error(f"Error loading classes: {str(e)}")
        return None

@app_commands.command(name="timetable", description="Get the timetable for a specific class and date")
@app_commands.describe(
    class_name="Class name (e.g., 1A, 2B, 3C, 4D)",
    date="Date in DD/MM/YYYY format (defaults to today)"
)
async def timetable(interaction: discord.Interaction, class_name: str, date: str = None):
    logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /timetable - Inputs: class_name={class_name}, date={date}")
    
    if not interaction.channel.permissions_for(interaction.guild.me).send_messages:
        logger.error(f"Bot lacks send_messages permission in channel {interaction.channel_id}")
        await interaction.response.send_message("Error: Bot lacks permission to send messages in this channel.", ephemeral=True)
        return
    
    if date is None:
        date = datetime.now().strftime('%d/%m/%Y')
        logger.info(f"Using default date: {date}")
    
    try:
        date_obj = datetime.strptime(date, '%d/%m/%Y')
        normalized_date = date_obj.strftime('%d/%m/%Y')
    except ValueError:
        logger.error(f"Invalid date format: {date}")
        await interaction.response.send_message("Error: Invalid date format. Use DD/MM/YYYY (e.g., 03/09/2024)", ephemeral=True)
        return
    
    result = get_timetable(class_name, normalized_date)
    
    embed = discord.Embed(
        title=f"Timetable for {class_name} on {normalized_date}",
        description="Schedule for the requested class and date.",
        color=0x00b7eb
    )
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(
        text="Use DD/MM/YYYY for dates. Contact the bot owner for issues.",
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    
    if isinstance(result, str):
        embed.add_field(name="Lessons", value=result, inline=False)
    else:
        lessons = "\n".join(result) if result else "No lessons scheduled."
        embed.add_field(name="Lessons", value=lessons, inline=False)
    
    view = create_timetable_view(class_name, normalized_date)
    
    await interaction.response.send_message(embed=embed, view=view)

def create_activities_view(current_date: str) -> discord.ui.View:
    """Helper function to create a view with activities buttons."""
    view = discord.ui.View(timeout=None)
    
    async def previous_day_activities(interaction: discord.Interaction):
        logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Action: Previous Day Activities button - Inputs: date={current_date}")
        try:
            date_obj = datetime.strptime(current_date, '%d/%m/%Y')
            prev_day = date_obj - timedelta(days=1)
            prev_date = prev_day.strftime('%d/%m/%Y')
        except ValueError:
            logger.error(f"Invalid date format in button: {current_date}")
            await interaction.response.send_message("Error: Invalid date format in button action.", ephemeral=True)
            return
        
        result = get_activities(prev_date)
        
        embed = discord.Embed(
            title=f"Activities on {prev_date}",
            description="Activities and remarks for the requested date.",
            color=0x00b7eb
        )
        embed.set_thumbnail(url=bot.user.avatar.url)
        embed.set_footer(
            text="Use DD/MM/YYYY for dates. Contact the bot owner for issues.",
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        
        if isinstance(result, str):
            embed.add_field(name="Error", value=result, inline=False)
        else:
            if 'message' in result:
                embed.add_field(name="Note", value=result['message'], inline=False)
            activities = result['activities']
            if 'message' in activities:
                embed.add_field(name="Activities", value=activities['message'], inline=False)
            else:
                activities_text = ""
                for slot, activities_list in activities.items():
                    activities_text += f"**{slot}**:\n" + "\n".join([f"- {activity}" for activity in activities_list]) + "\n"
                embed.add_field(name="Activities", value=activities_text.strip() or "None", inline=False)
            remark = result.get('remark', '')
            embed.add_field(name="Remarks", value=remark if remark else "None", inline=False)
        
        new_view = create_activities_view(prev_date)
        
        await interaction.response.edit_message(embed=embed, view=new_view)
    
    previous_day_button = discord.ui.Button(label="Previous Day Activities", style=discord.ButtonStyle.secondary)
    previous_day_button.callback = previous_day_activities
    view.add_item(previous_day_button)
    
    async def next_day_activities(interaction: discord.Interaction):
        logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Action: Next Day Activities button - Inputs: date={current_date}")
        try:
            date_obj = datetime.strptime(current_date, '%d/%m/%Y')
            next_day = date_obj + timedelta(days=1)
            next_date = next_day.strftime('%d/%m/%Y')
        except ValueError:
            logger.error(f"Invalid date format in button: {current_date}")
            await interaction.response.send_message("Error: Invalid date format in button action.", ephemeral=True)
            return
        
        result = get_activities(next_date)
        
        embed = discord.Embed(
            title=f"Activities on {next_date}",
            description="Activities and remarks for the requested date.",
            color=0x00b7eb
        )
        embed.set_thumbnail(url=bot.user.avatar.url)
        embed.set_footer(
            text="Use DD/MM/YYYY for dates. Contact the bot owner for issues.",
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        
        if isinstance(result, str):
            embed.add_field(name="Error", value=result, inline=False)
        else:
            if 'message' in result:
                embed.add_field(name="Note", value=result['message'], inline=False)
            activities = result['activities']
            if 'message' in activities:
                embed.add_field(name="Activities", value=activities['message'], inline=False)
            else:
                activities_text = ""
                for slot, activities_list in activities.items():
                    activities_text += f"**{slot}**:\n" + "\n".join([f"- {activity}" for activity in activities_list]) + "\n"
                embed.add_field(name="Activities", value=activities_text.strip() or "None", inline=False)
            remark = result.get('remark', '')
            embed.add_field(name="Remarks", value=remark if remark else "None", inline=False)
        
        new_view = create_activities_view(next_date)
        
        await interaction.response.edit_message(embed=embed, view=new_view)
    
    next_day_button = discord.ui.Button(label="Next Day Activities", style=discord.ButtonStyle.secondary)
    next_day_button.callback = next_day_activities
    view.add_item(next_day_button)
    
    return view

def create_timetable_view(class_name: str, current_date: str) -> discord.ui.View:
    """Helper function to create a view with timetable buttons and class dropdown."""
    view = discord.ui.View(timeout=None)
    
    classes = get_available_classes()
    if classes:
        class_select = discord.ui.Select(
            placeholder="Select another class...",
            options=[
                discord.SelectOption(label=cls, value=cls, default=(cls == class_name))
                for cls in classes
            ],
            min_values=1,
            max_values=1
        )
        
        async def class_select_callback(interaction: discord.Interaction):
            selected_class = class_select.values[0]
            logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Action: Timetable class selection - Inputs: class_name={selected_class}, date={current_date}")
            
            result = get_timetable(selected_class, current_date)
            
            embed = discord.Embed(
                title=f"Timetable for {selected_class} on {current_date}",
                description="Schedule for the requested class and date.",
                color=0x00b7eb
            )
            embed.set_thumbnail(url=bot.user.avatar.url)
            embed.set_footer(
                text="Use DD/MM/YYYY for dates. Contact the bot owner for issues.",
                icon_url=interaction.user.avatar.url if interaction.user.avatar else None
            )
            
            if isinstance(result, str):
                embed.add_field(name="Lessons", value=result, inline=False)
            else:
                lessons = "\n".join(result) if result else "No lessons scheduled."
                embed.add_field(name="Lessons", value=lessons, inline=False)
            
            new_view = create_timetable_view(selected_class, current_date)
            
            await interaction.response.edit_message(embed=embed, view=new_view)
        
        class_select.callback = class_select_callback
        view.add_item(class_select)
    
    async def show_activities(interaction: discord.Interaction):
        logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Action: Show Activities button - Inputs: date={current_date}")
        try:
            date_obj = datetime.strptime(current_date, '%d/%m/%Y')
            button_date = date_obj.strftime('%d/%m/%Y')
        except ValueError:
            logger.error(f"Invalid date format in button: {current_date}")
            await interaction.response.send_message("Error: Invalid date format in button action.", ephemeral=True)
            return
        
        result = get_activities(button_date)
        
        embed = discord.Embed(
            title=f"Activities on {button_date}",
            description="Activities and remarks for the requested date.",
            color=0x00b7eb
        )
        embed.set_thumbnail(url=bot.user.avatar.url)
        embed.set_footer(
            text="Use DD/MM/YYYY for dates. Contact the bot owner for issues.",
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        
        if isinstance(result, str):
            embed.add_field(name="Error", value=result, inline=False)
        else:
            if 'message' in result:
                embed.add_field(name="Note", value=result['message'], inline=False)
            activities = result['activities']
            if 'message' in activities:
                embed.add_field(name="Activities", value=activities['message'], inline=False)
            else:
                activities_text = ""
                for slot, activities_list in activities.items():
                    activities_text += f"**{slot}**:\n" + "\n".join([f"- {activity}" for activity in activities_list]) + "\n"
                embed.add_field(name="Activities", value=activities_text.strip() or "None", inline=False)
            remark = result.get('remark', '')
            embed.add_field(name="Remarks", value=remark if remark else "None", inline=False)
        
        activities_view = create_activities_view(button_date)
        
        await interaction.response.send_message(embed=embed, view=activities_view, ephemeral=True)
    
    activities_button = discord.ui.Button(label="Show Activities", style=discord.ButtonStyle.primary)
    activities_button.callback = show_activities
    view.add_item(activities_button)
    
    async def previous_day_timetable(interaction: discord.Interaction):
        logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Action: Previous Day Timetable button - Inputs: class_name={class_name}, date={current_date}")
        try:
            date_obj = datetime.strptime(current_date, '%d/%m/%Y')
            prev_day = date_obj - timedelta(days=1)
            prev_date = prev_day.strftime('%d/%m/%Y')
        except ValueError:
            logger.error(f"Invalid date format in button: {current_date}")
            await interaction.response.send_message("Error: Invalid date format in button action.", ephemeral=True)
            return
        
        result = get_timetable(class_name, prev_date)
        
        embed = discord.Embed(
            title=f"Timetable for {class_name} on {prev_date}",
            description="Schedule for the requested class and date.",
            color=0x00b7eb
        )
        embed.set_thumbnail(url=bot.user.avatar.url)
        embed.set_footer(
            text="Use DD/MM/YYYY for dates. Contact the bot owner for issues.",
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        
        if isinstance(result, str):
            embed.add_field(name="Lessons", value=result, inline=False)
        else:
            lessons = "\n".join(result) if result else "No lessons scheduled."
            embed.add_field(name="Lessons", value=lessons, inline=False)
        
        new_view = create_timetable_view(class_name, prev_date)
        
        await interaction.response.edit_message(embed=embed, view=new_view)
    
    previous_day_button = discord.ui.Button(label="⬅️", style=discord.ButtonStyle.secondary)
    previous_day_button.callback = previous_day_timetable
    view.add_item(previous_day_button)

    async def next_day_timetable(interaction: discord.Interaction):
        logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Action: Next Day Timetable button - Inputs: class_name={class_name}, date={current_date}")
        try:
            date_obj = datetime.strptime(current_date, '%d/%m/%Y')
            next_day = date_obj + timedelta(days=1)
            next_date = next_day.strftime('%d/%m/%Y')
        except ValueError:
            logger.error(f"Invalid date format in button: {current_date}")
            await interaction.response.send_message("Error: Invalid date format in button action.", ephemeral=True)
            return
        
        result = get_timetable(class_name, next_date)
        
        embed = discord.Embed(
            title=f"Timetable for {class_name} on {next_date}",
            description="Schedule for the requested class and date.",
            color=0x00b7eb
        )
        embed.set_thumbnail(url=bot.user.avatar.url)
        embed.set_footer(
            text="Use DD/MM/YYYY for dates. Contact the bot owner for issues.",
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        
        if isinstance(result, str):
            embed.add_field(name="Lessons", value=result, inline=False)
        else:
            lessons = "\n".join(result) if result else "No lessons scheduled."
            embed.add_field(name="Lessons", value=lessons, inline=False)
        
        new_view = create_timetable_view(class_name, next_date)
        
        await interaction.response.edit_message(embed=embed, view=new_view)
    
    next_day_button = discord.ui.Button(label="➡️", style=discord.ButtonStyle.secondary)
    next_day_button.callback = next_day_timetable
    view.add_item(next_day_button)
    

    
    return view

@app_commands.command(name="activities", description="Get activities for a specific date from the server")
@app_commands.describe(
    date="Date in DD/MM/YYYY format (defaults to today)"
)
async def activities(interaction: discord.Interaction, date: str = None):
    logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /activities - Inputs: date={date}")
    
    if not interaction.channel.permissions_for(interaction.guild.me).send_messages:
        logger.error(f"Bot lacks send_messages permission in channel {interaction.channel_id}")
        await interaction.response.send_message("Error: Bot lacks permission to send messages in this channel.", ephemeral=True)
        return
    
    if date is None:
        date = datetime.now().strftime('%d/%m/%Y')
        logger.info(f"Using default date: {date}")
    
    try:
        date_obj = datetime.strptime(date, '%d/%m/%Y')
        normalized_date = date_obj.strftime('%d/%m/%Y')
    except ValueError:
        logger.error(f"Invalid date format: {date}")
        await interaction.response.send_message("Error: Invalid date format. Use DD/MM/YYYY (e.g., 03/09/2024)", ephemeral=True)
        return
    
    result = get_activities(normalized_date)
    
    embed = discord.Embed(
        title=f"Activities on {normalized_date}",
        description="Activities and remarks for the requested date.",
        color=0x00b7eb
    )
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(
        text="Use DD/MM/YYYY for dates. Contact the bot owner for issues.",
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    
    if isinstance(result, str):
        embed.add_field(name="Error", value=result, inline=False)
    else:
        if 'message' in result:
            embed.add_field(name="Note", value=result['message'], inline=False)
        activities = result['activities']
        if 'message' in activities:
            embed.add_field(name="Activities", value=activities['message'], inline=False)
        else:
            activities_text = ""
            for slot, activities_list in activities.items():
                activities_text += f"**{slot}**:\n" + "\n".join([f"- {activity}" for activity in activities_list]) + "\n"
            embed.add_field(name="Activities", value=activities_text.strip() or "None", inline=False)
        remark = result.get('remark', '')
        embed.add_field(name="Remarks", value=remark if remark else "None", inline=False)
    
    view = create_activities_view(normalized_date)
    
    await interaction.response.send_message(embed=embed, view=view)

@app_commands.command(name="qrcode", description="Generate a QR code for a given URL with a selected style and color")
@app_commands.describe(
    url="The URL to encode in the QR code (e.g., https://example.com)",
    color="QR code color (e.g., red, #FF0000, blue; defaults to black)"
)
async def qrcode(interaction: discord.Interaction, url: str, color: str = None):
    log_message = f"User: {interaction.user.id} ({interaction.user.name}) - Command: /qrcode - Inputs: url={url}, style=horizontal_gradient, color={color or 'black'}"
    logger.info(log_message)
    qrcode_logger.info(log_message)
    
    if not interaction.channel.permissions_for(interaction.guild.me).send_messages:
        logger.error(f"Bot lacks send_messages permission in channel {interaction.channel_id}")
        await interaction.response.send_message("Error: Bot lacks permission to send messages in this channel.", ephemeral=True)
        return
    if not interaction.channel.permissions_for(interaction.guild.me).attach_files:
        logger.error(f"Bot lacks attach_files permission in channel {interaction.channel_id}")
        await interaction.response.send_message("Error: Bot lacks permission to attach files in this channel.", ephemeral=True)
        return
    
    if not (url.startswith('http://') or url.startswith('https://')):
        logger.error(f"Invalid URL format: {url}")
        await interaction.response.send_message("Error: Invalid URL format. Must start with http:// or https://", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        qr_bytes = generate_qr_code(url, style="horizontal_gradient", color=color)
    except Exception as e:
        logger.error(f"Failed to generate QR code: {str(e)}")
        qrcode_logger.error(f"User: {interaction.user.id} ({interaction.user.name}) - Failed to generate QR code: {str(e)}")
        await interaction.followup.send("Error: Failed to generate QR code. Please try again or contact the bot owner.", ephemeral=True)
        return
    
    qr_file = discord.File(qr_bytes, filename="qrcode.png")
    
    embed = discord.Embed(
        title="QR Code",
        description=f"QR code for: {url}\nStyle: Horizontal Gradient\nColor: {color or 'Black'}",
        color=0x00b7eb
    )
    embed.set_image(url="attachment://qrcode.png")
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(
        text="Select a style below to regenerate the QR code.",
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    
    view = create_qr_view(url, current_style="horizontal_gradient", current_color=color)
    
    await interaction.followup.send(embed=embed, file=qr_file, view=view)

def create_qr_view(url: str, current_style: str, current_color: str = None) -> discord.ui.View:
    """Helper function to create a view with QR code style dropdown."""
    view = discord.ui.View(timeout=None)
    
    style_options = [
        discord.SelectOption(
            label="Solid Color",
            value="solid",
            description="Black QR code on white background",
            default=(current_style == "solid")
        ),
        discord.SelectOption(
            label="Horizontal Gradient",
            value="horizontal_gradient",
            description="Gradient from white to red to blue (left to right)",
            default=(current_style == "horizontal_gradient")
        ),
        discord.SelectOption(
            label="Vertical Gradient",
            value="vertical_gradient",
            description="Gradient from white to red to blue (top to bottom)",
            default=(current_style == "vertical_gradient")
        ),
        discord.SelectOption(
            label="Radial Gradient",
            value="radial_gradient",
            description="Gradient from white to red to blue (center outward)",
            default=(current_style == "radial_gradient")
        )
    ]
    
    style_select = discord.ui.Select(
        placeholder="Select QR code style...",
        options=style_options,
        min_values=1,
        max_values=1
    )
    
    async def style_select_callback(interaction: discord.Interaction):
        selected_style = style_select.values[0]
        log_message = f"User: {interaction.user.id} ({interaction.user.name}) - Action: QR code style selection - Inputs: url={url}, style={selected_style}, color={current_color or 'black'}"
        logger.info(log_message)
        qrcode_logger.info(log_message)
        
        try:
            qr_bytes = generate_qr_code(url, style=selected_style, color=current_color)
        except Exception as e:
            logger.error(f"Failed to generate QR code: {str(e)}")
            qrcode_logger.error(f"User: {interaction.user.id} ({interaction.user.name}) - Failed to generate QR code: {str(e)}")
            await interaction.response.send_message("Error: Failed to generate QR code. Please try again or contact the bot owner.", ephemeral=True)
            return
        
        qr_file = discord.File(qr_bytes, filename="qrcode.png")
        
        style_names = {
            "solid": "Solid Color",
            "horizontal_gradient": "Horizontal Gradient",
            "vertical_gradient": "Vertical Gradient",
            "radial_gradient": "Radial Gradient"
        }
        embed = discord.Embed(
            title="QR Code",
            description=f"QR code for: {url}\nStyle: {style_names[selected_style]}\nColor: {current_color or 'Black'}",
            color=0x00b7eb
        )
        embed.set_image(url="attachment://qrcode.png")
        embed.set_thumbnail(url=bot.user.avatar.url)
        embed.set_footer(
            text="Select a style below to regenerate the QR code.",
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        
        new_view = create_qr_view(url, current_style=selected_style, current_color=current_color)
        
        await interaction.response.edit_message(embed=embed, attachments=[qr_file], view=new_view)
    
    style_select.callback = style_select_callback
    view.add_item(style_select)
    
    return view

@app_commands.command(name="ask_ai", description="Ask a question to the AI")
@app_commands.describe(
    query="Your question or prompt for the AI",
    model="The AI model to use (defaults to gpt-4o-mini)"
)
@app_commands.choices(model=[
    app_commands.Choice(name="GPT-4o-mini", value="gpt-4o-mini"),
    app_commands.Choice(name="DeepSeek V3", value="deepseek-v3")
])
async def ask_ai(interaction: discord.Interaction, query: str, model: str = "gpt-4o-mini"):
    logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /ask_ai - Inputs: query={query}, model={model}")
    
    if not interaction.channel.permissions_for(interaction.guild.me).send_messages:
        logger.error(f"Bot lacks send_messages permission in channel {interaction.channel_id}")
        await interaction.response.send_message("Error: Bot lacks permission to send messages in this channel.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    messages = [{'role': 'user', 'content': query}]
    
    response = gpt_35_api(messages, model=model)
    
    embed = discord.Embed(
        title="AI Response",
        description=f"**Query**: {query}",
        color=0x00b7eb
    )
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(
        text=f"Powered by {model.replace('-', ' ').title()}. Contact the bot owner for issues.",
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    
    if response.startswith("Error:"):
        embed.add_field(name="Error", value=response, inline=False)
    else:
        embed.add_field(name="Response", value=response, inline=False)
    
    await interaction.followup.send(embed=embed)


@app_commands.command(name="avatar", description="Get a user's avatar")
@app_commands.describe(
    user="The user to get the avatar for (defaults to you)"
)
async def avatar_command(interaction: discord.Interaction, user: discord.User = None):
    logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /avatar - Inputs: user={user.id if user else interaction.user.id}")
    
    if not interaction.channel.permissions_for(interaction.guild.me).send_messages:
        logger.error(f"Bot lacks send_messages permission in channel {interaction.channel_id}")
        await interaction.response.send_message("Error: Bot lacks permission to send messages in this channel.", ephemeral=True)
        return
    
    target_user = user if user else interaction.user
    avatar_url = target_user.avatar.url if target_user.avatar else target_user.default_avatar.url
    
    embed = discord.Embed(
        title=f"{target_user.name}'s Avatar",
        description=f"**Username**: {target_user.name}\n**User ID**: {target_user.id}",
        color=0x00b7eb
    )
    embed.set_image(url=avatar_url)
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(
        text="Contact the bot owner for issues.",
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    
    await interaction.response.send_message(embed=embed)
    logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /avatar - Response sent for user {target_user.id}")

@app_commands.command(name="server", description="Get information about the current server")
async def server_command(interaction: discord.Interaction):
    logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /server - Inputs: guild={interaction.guild.id if interaction.guild else 'None'}")
    
    if not interaction.channel.permissions_for(interaction.guild.me).send_messages:
        logger.error(f"Bot lacks send_messages permission in channel {interaction.channel_id}")
        await interaction.response.send_message("Error: Bot lacks permission to send messages in this channel.", ephemeral=True)
        return
    
    if not interaction.guild:
        logger.error(f"Command /server used in DMs by user {interaction.user.id}")
        await interaction.response.send_message("Error: This command can only be used in a server.", ephemeral=True)
        return
    
    guild = interaction.guild
    
    embed = discord.Embed(
        title=f"{guild.name} Server Info",
        color=0x00b7eb
    )
    embed.set_thumbnail(url=guild.icon.url if guild.icon else bot.user.avatar.url)
    embed.set_footer(
        text="Contact the bot owner for issues.",
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    
    embed.add_field(name="Server ID", value=str(guild.id), inline=True)
    embed.add_field(name="Member Count", value=guild.member_count, inline=True)
    embed.add_field(name="Owner", value=f"{guild.owner} ({guild.owner_id})", inline=False)
    embed.add_field(name="Created At", value=guild.created_at.strftime('%Y-%m-%d %H:%M:%S UTC'), inline=False)
    embed.add_field(name="Channels", value=len(guild.channels), inline=True)
    embed.add_field(name="Roles", value=len(guild.roles), inline=True)
    
    await interaction.response.send_message(embed=embed)
    logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /server - Response sent for guild {guild.id}")

@app_commands.command(name="suggestion", description="Send a suggestion to the bot developer")
@app_commands.describe(
    message="Your suggestion"
)
async def suggestion_command(interaction: discord.Interaction, message: str):
    logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /suggestion - Inputs: message={message}")
    
    if not interaction.channel.permissions_for(interaction.guild.me).send_messages:
        logger.error(f"Bot lacks send_messages permission in channel {interaction.channel_id}")
        await interaction.response.send_message("Error: Bot lacks permission to send messages in this channel.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        dev_user = await bot.fetch_user(int(DEV_USER_ID))
        suggestion_embed = discord.Embed(
            title="New Suggestion",
            description=f"**Suggestion**: {message}\n**From**: {interaction.user.name} ({interaction.user.id})",
            color=0x00b7eb
        )
        suggestion_embed.set_thumbnail(url=bot.user.avatar.url)
        suggestion_embed.set_footer(text="Sent via /suggestion command")
        await dev_user.send(embed=suggestion_embed)
        
        confirmation_embed = discord.Embed(
            title="Suggestion Sent",
            description="Your suggestion has been sent to the bot developer. Thank you!",
            color=0x00b7eb
        )
        confirmation_embed.set_thumbnail(url=bot.user.avatar.url)
        confirmation_embed.set_footer(
            text="Contact the bot owner for issues.",
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        
        await interaction.followup.send(embed=confirmation_embed)
        logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /suggestion - Suggestion sent to {DEV_USER_ID}")
    except discord.errors.Forbidden:
        logger.error(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /suggestion - Forbidden to send DM to {DEV_USER_ID}")
        await interaction.followup.send("Error: Cannot send suggestion (developer may have DMs disabled).", ephemeral=True)
    except Exception as e:
        logger.error(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /suggestion - Failed to send suggestion: {str(e)}")
        await interaction.followup.send(f"Error: Failed to send suggestion: {str(e)}", ephemeral=True)

@app_commands.command(name="dev", description="Developer command to view bot server info")
@app_commands.describe(
    server_name="Name of a specific server to view details (optional)"
)
async def dev_command(interaction: discord.Interaction, server_name: str = None):
    if str(interaction.user.id) != DEV_USER_ID:
        logger.warning(f"Unauthorized user {interaction.user.id} ({interaction.user.name}) attempted /dev command")
        await interaction.response.send_message("Error: This command is restricted to the bot developer.", ephemeral=True)
        return
    
    logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /dev - Inputs: server_name={server_name}")
    
    await interaction.response.defer(ephemeral=True)
    
    embed = discord.Embed(
        title="Bot Server Info",
        color=0x00b7eb
    )
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(
        text="Developer command",
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    
    if server_name:
        target_guild = None
        for guild in bot.guilds:
            if guild.name.lower() == server_name.lower():
                target_guild = guild
                break
        
        if target_guild:
            embed.description = f"Details for server: **{target_guild.name}**"
            embed.add_field(name="Server ID", value=str(target_guild.id), inline=True)
            embed.add_field(name="Member Count", value=target_guild.member_count, inline=True)
            embed.add_field(name="Owner", value=f"{target_guild.owner} ({target_guild.owner_id})", inline=False)
            embed.add_field(name="Created At", value=target_guild.created_at.strftime('%Y-%m-%d %H:%M:%S UTC'), inline=False)
            embed.add_field(name="Channels", value=len(target_guild.channels), inline=True)
            embed.add_field(name="Roles", value=len(target_guild.roles), inline=True)
        else:
            embed.description = f"No server found with name: **{server_name}**"
    else:
        guild_count = len(bot.guilds)
        guild_names = ", ".join([guild.name for guild in bot.guilds]) or "None"
        embed.description = f"Bot is in **{guild_count}** server(s)"
        embed.add_field(name="Servers", value=guild_names, inline=False)
    
    await interaction.followup.send(embed=embed, ephemeral=True)
    logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /dev - Response sent")

@app_commands.command(name="pm", description="Developer command to send a DM to a user")
@app_commands.describe(
    user_id="The ID of the user to DM",
    message="The message to send"
)
async def pm_command(interaction: discord.Interaction, user_id: str, message: str):
    if str(interaction.user.id) != DEV_USER_ID:
        logger.warning(f"Unauthorized user {interaction.user.id} ({interaction.user.name}) attempted /pm command")
        await interaction.response.send_message("Error: This command is restricted to the bot developer.", ephemeral=True)
        return
    
    logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /pm - Inputs: user_id={user_id}, message={message}")
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        user = await bot.fetch_user(int(user_id))
        embed = discord.Embed(
            title="Message from Bot Developer",
            description=message,
            color=0x00b7eb
        )
        embed.set_thumbnail(url=bot.user.avatar.url)
        embed.set_footer(text="Sent via developer command")
        await user.send(embed=embed)
        await interaction.followup.send(f"Message sent to user {user_id} successfully.", ephemeral=True)
        logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /pm - DM sent to {user_id}")
    except ValueError:
        await interaction.followup.send("Error: Invalid user ID format.", ephemeral=True)
        logger.error(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /pm - Invalid user ID: {user_id}")
    except discord.errors.NotFound:
        await interaction.followup.send("Error: User not found.", ephemeral=True)
        logger.error(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /pm - User not found: {user_id}")
    except discord.errors.Forbidden:
        await interaction.followup.send("Error: Cannot send DM (user may have DMs disabled or blocked the bot).", ephemeral=True)
        logger.error(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /pm - Forbidden to send DM to {user_id}")
    except Exception as e:
        await interaction.followup.send(f"Error: Failed to send DM: {str(e)}", ephemeral=True)
        logger.error(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /pm - Failed to send DM to {user_id}: {str(e)}")

@app_commands.command(name="weather", description="Get the 9-day weather forecast for Hong Kong")
async def weather(interaction: discord.Interaction):
    logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /weather - Inputs: None")
    
    if not interaction.channel.permissions_for(interaction.guild.me).send_messages:
        logger.error(f"Bot lacks send_messages permission in channel {interaction.channel_id}")
        await interaction.response.send_message("Error: Bot lacks permission to send messages in this channel.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    forecast_data = get_weather()
    
    embed = discord.Embed(
        title="Hong Kong 9-Day Weather Forecast",
        description="Latest 9-day weather forecast from Hong Kong Observatory",
        color=0x00b7eb
    )
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(
        text="Source: Hong Kong Observatory (fetched live). Contact the bot owner for issues.",
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    
    if forecast_data and forecast_data[0].startswith("Error:"):
        embed.add_field(name="Error", value=forecast_data[0], inline=False)
    else:
        forecast_text = "\n".join(forecast_data) or "No data available."
        embed.add_field(name="Forecast", value=forecast_text, inline=False)
    
    await interaction.followup.send(embed=embed)

@app_commands.command(name="help", description="Show help for using the bot's commands")
async def help_command(interaction: discord.Interaction):
    logger.info(f"User: {interaction.user.id} ({interaction.user.name}) - Command: /help - Inputs: None")
    
    if not interaction.channel.permissions_for(interaction.guild.me).send_messages:
        logger.error(f"Bot lacks send_messages permission in channel {interaction.channel_id}")
        await interaction.response.send_message("Error: Bot lacks permission to send messages in this channel.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    embed = discord.Embed(
        title="Bot Help",
        description=(
            "This bot helps you check class timetables, school activities, generate QR codes, ask AI questions, check the latest 9-day weather forecast, and more. "
            "Use the commands below or ping the bot to chat with the AI!\n"
            "Invite the bot to your server: [Click here](https://discord.com/oauth2/authorize?client_id=1131163159097516123&permissions=8&integration_type=0&scope=bot+applications.commands)"
        ),
        color=0x00b7eb
    )
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(
        text="Use DD/MM/YYYY for dates. Contact the bot owner for issues.",
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    
    # ... (Other command descriptions unchanged)
    
    embed.add_field(
        name="/weather",
        value=(
            "**Description**: Get the latest 9-day weather forecast for Hong Kong (fetched live).\n"
            "**Parameters**: None\n"
            "**Output**: Embed with weather forecast for the next 9 days from Hong Kong Observatory.\n"
            "**Example**: `/weather`\n"
        ),
        inline=False
    )

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return
    
    if bot.user in message.mentions:
        logger.info(f"User: {message.author.id} ({message.author.name}) - Action: Ping AI - Inputs: query={message.content}")
        
        if not message.channel.permissions_for(message.guild.me).send_messages:
            logger.error(f"Bot lacks send_messages permission in channel {message.channel.id}")
            return
        
        query = message.content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()
        
        if not query:
            logger.info(f"User: {message.author.id} ({message.author.name}) - Action: Ping AI - Inputs: None (empty query)")
            embed = discord.Embed(
                title="AI Response",
                description="Please provide a question or prompt after mentioning me!",
                color=0x00b7eb
            )
            embed.set_thumbnail(url=bot.user.avatar.url)
            embed.set_footer(
                text="Powered by GPT-4o-mini. Contact the bot owner for issues.",
                icon_url=message.author.avatar.url if message.author.avatar else None
            )
            await message.channel.send(embed=embed)
            return
        
        messages = [{'role': 'user', 'content': query}]
        
        response = gpt_35_api(messages)
        
        embed = discord.Embed(
            title="AI Response",
            description=f"**Query**: {query}",
            color=0x00b7eb
        )
        embed.set_thumbnail(url=bot.user.avatar.url)
        embed.set_footer(
            text="Powered by GPT-4o-mini. Contact the bot owner for issues.",
            icon_url=message.author.avatar.url if message.author.avatar else None
        )
        
        if response.startswith("Error:"):
            embed.add_field(name="Error", value=response, inline=False)
        else:
            embed.add_field(name="Response", value=response, inline=False)
        
        await message.channel.send(embed=embed)
    
    await bot.process_commands(message)

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    try:
        logger.info("Attempting to sync slash commands globally...")
        synced_commands = await tree.sync()
        logger.info(f"Slash commands synced globally: {len(synced_commands)} commands")
        for command in synced_commands:
            logger.info(f"Synced command: {command.name}")
    except discord.errors.Forbidden:
        logger.error("Bot lacks permission to sync commands. Ensure it has 'applications.commands' scope.")
    except discord.errors.HTTPException as e:
        logger.error(f"Error syncing commands: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during command sync: {e}")

# Register commands
tree.add_command(timetable)
tree.add_command(activities)
tree.add_command(qrcode)
tree.add_command(ask_ai)
tree.add_command(help_command)
tree.add_command(avatar_command)
tree.add_command(server_command)
tree.add_command(suggestion_command)
tree.add_command(dev_command)
tree.add_command(pm_command)
tree.add_command(weather)

# Run the bot
bot.run(TOKEN)