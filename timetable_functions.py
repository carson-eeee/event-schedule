import json
from datetime import datetime, timedelta
import os
import logging
import requests
from requests.exceptions import RequestException

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_cycle_day(date_str):
    """
    Retrieves the cycle day for a given date from cycleal.json.
    
    Args:
        date_str (str): Date in DD/MM/YYYY format (e.g., '03/09/2024')
        
    Returns:
        str: Cycle day (e.g., 'A', 'B', or '/' for no school day)
    """
    try:
        # Normalize and validate date format
        date_obj = datetime.strptime(date_str, '%d/%m/%Y')
        normalized_date = date_obj.strftime('%d/%m/%Y')
        
        # Use relative path for test_data
        file_path = os.path.join('test_data', 'cycleal.json')
        resolved_path = os.path.abspath(file_path)
        logger.info(f"Attempting to load cycleal.json: {resolved_path}")
        
        with open(file_path, 'r', encoding='utf-8') as file:
            cycle_data = json.load(file)
        
        # Check if date exists in cycleal.json
        if normalized_date not in cycle_data:
            return f"Error: Date {normalized_date} not found in cycleal.json"
        
        return cycle_data[normalized_date]
    except FileNotFoundError:
        error_msg = f"Error: cycleal.json file not found at {resolved_path}. Please ensure the 'test_data' folder contains 'cycleal.json'."
        logger.error(error_msg)
        return error_msg
    except ValueError:
        return "Error: Invalid date format. Use DD/MM/YYYY (e.g., 03/09/2024)"
    except Exception as e:
        return f"Error: {str(e)}"

def get_timetable(class_name, date_str):
    """
    Retrieves the timetable for a given class and date, standardizing periods as Lesson 1–6.
    
    Args:
        class_name (str): Class name (e.g., '1A', '2B', '3C')
        date_str (str): Date in DD/MM/YYYY format (e.g., '03/09/2024')
        
    Returns:
        list: List of timetable entries (strings like 'Lesson X: Subject') or error message
    """
    try:
        # Normalize and validate date format
        date_obj = datetime.strptime(date_str, '%d/%m/%Y')
        normalized_date = date_obj.strftime('%d/%m/%Y')
        
        # Get cycle day
        cycle_day = get_cycle_day(normalized_date)
        
        # Handle non-school days or errors
        if cycle_day == '/':
            return f"No school on {normalized_date}"
        elif cycle_day.startswith("Error"):
            return cycle_day
        
        # Load timetable data
        file_path = os.path.join('test_data', 'timetale.json')
        resolved_path = os.path.abspath(file_path)
        logger.info(f"Attempting to load timetale.json: {resolved_path}")
        
        with open(file_path, 'r', encoding='utf-8') as file:
            timetable_data = json.load(file)
        
        # Validate class name
        if class_name not in timetable_data:
            return f"Error: Class {class_name} not found in timetale.json"
        
        # Validate cycle day for the class
        if cycle_day not in timetable_data[class_name]:
            return f"Error: Cycle day {cycle_day} not found for class {class_name}"
        
        # Get timetable entries
        timetable = timetable_data[class_name][cycle_day]
        
        # Standardize to Lesson 1–6
        formatted_timetable = []
        for index, item in enumerate(timetable, start=1):
            lesson_num = min(index, 6)
            if isinstance(item, dict):
                try:
                    subject = item.get('subject', 'Unknown')
                    formatted_timetable.append(f"Lesson {lesson_num}: {subject}")
                except (KeyError, TypeError):
                    return f"Error: Invalid timetable entry format for class {class_name} on cycle day {cycle_day}"
            elif isinstance(item, str):
                formatted_timetable.append(f"Lesson {lesson_num}: {item}")
            else:
                return f"Error: Invalid timetable entry type for class {class_name} on cycle day {cycle_day}"
        
        # Pad with empty lessons if fewer than 6
        while len(formatted_timetable) < 6:
            formatted_timetable.append(f"Lesson {len(formatted_timetable) + 1}: None")
        
        return formatted_timetable
    except FileNotFoundError:
        error_msg = f"Error: timetale.json file not found at {resolved_path}. Please ensure the 'test_data' folder contains 'timetale.json'."
        logger.error(error_msg)
        return error_msg
    except ValueError:
        return "Error: Invalid date format. Use DD/MM/YYYY (e.g., 03/09/2024)"
    except Exception as e:
        return f"Error: {str(e)}"

def get_activities(date_str):
    """
    Retrieves all activities and remark for a given date from the server.
    If the date is not found, returns activities and remark for the closest available date.
    
    Args:
        date_str (str): Date in DD/MM/YYYY format (e.g., '03/09/2024')
        
    Returns:
        dict: Dictionary with slot names as keys and lists of activities as values, remark, or error message
    """
    try:
        # Normalize and validate date format
        date_obj = datetime.strptime(date_str, '%d/%m/%Y')
        # Remove leading zeros for JSON search (e.g., '03/09/2024' -> '3/9/2024')
        search_date = f"{int(date_obj.day)}/{int(date_obj.month)}/{date_obj.year}"
        normalized_date = date_obj.strftime('%d/%m/%Y')
        
        # Fetch data from URL
        url = "https://iot.spyc.hk/event-schedule"
        logger.info(f"Attempting to fetch activities from: {url}")
        response = requests.get(url, timeout=5)
        
        # Check HTTP status
        if response.status_code != 200:
            error_msg = f"Error: Failed to fetch activities. HTTP {response.status_code}"
            logger.error(error_msg)
            return error_msg
        
        # Parse JSON
        try:
            event_data = response.json()
        except ValueError:
            error_msg = "Error: Invalid JSON data received from server"
            logger.error(error_msg)
            return error_msg
        
        logger.info(f"Successfully fetched activities data for date: {normalized_date}")
        
        # Get all available dates
        available_dates = list(event_data['rows'].keys())
        if not available_dates:
            return "Error: No dates found in server data"
        
        # Check if the requested date exists
        if search_date in event_data['rows']:
            date_data = event_data['rows'][search_date]['slots']
            remark = event_data['rows'][search_date].get('remark', '')
            activities = get_activities_for_date(date_data, normalized_date)
            return {'activities': activities, 'remark': remark}
        else:
            # Find the closest date
            target_date = date_obj
            closest_date = None
            min_diff = None
            
            for date_key in available_dates:
                try:
                    # Parse date_key, assuming it might be in D/M/YYYY or DD/MM/YYYY
                    try:
                        available_date = datetime.strptime(date_key, '%d/%m/%Y')
                    except ValueError:
                        # Try parsing with leading zeros
                        parts = date_key.split('/')
                        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                        available_date = datetime.strptime(f"{day:02d}/{month:02d}/{year}", '%d/%m/%Y')
                    
                    diff = abs((target_date - available_date).days)
                    if min_diff is None or diff < min_diff:
                        min_diff = diff
                        closest_date = date_key
                except ValueError:
                    continue
            
            if closest_date is None:
                return "Error: No valid dates found in server data"
            
            date_data = event_data['rows'][closest_date]['slots']
            remark = event_data['rows'][closest_date].get('remark', '')
            # Convert closest_date to DD/MM/YYYY for display
            closest_date_obj = datetime.strptime(closest_date, '%d/%m/%Y')
            closest_date_normalized = closest_date_obj.strftime('%d/%m/%Y')
            activities = get_activities_for_date(date_data, closest_date_normalized)
            return {
                'message': f"No activities found for {normalized_date}. Showing activities for closest date: {closest_date_normalized}",
                'activities': activities,
                'remark': remark
            }
    
    except requests.Timeout:
        error_msg = "Error: Request to server timed out. Please try again later."
        logger.error(error_msg)
        return error_msg
    except requests.ConnectionError:
        error_msg = "Error: Failed to connect to server. Check your internet connection."
        logger.error(error_msg)
        return error_msg
    except RequestException as e:
        error_msg = f"Error: Failed to fetch activities: {str(e)}"
        logger.error(error_msg)
        return error_msg
    except ValueError:
        return "Error: Invalid date format. Use DD/MM/YYYY (e.g., 03/09/2024)"
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        logger.error(error_msg)
        return error_msg

def get_activities_for_date(date_data, date_str):
    """
    Helper function to extract activities from date_data for a given date.
    
    Args:
        date_data (dict): Slot data for the date
        date_str (str): Date in DD/MM/YYYY format for display
        
    Returns:
        dict: Dictionary with slot names as keys and lists of activities as values
    """
    activities = {}
    
    # Iterate through each slot (e.g., AM, PM, AM_L, etc.)
    for slot_name, slot_data in date_data.items():
        slot_activities = []
        
        # Collect activities from S1 to S6
        for grade in ['S1', 'S2', 'S3', 'S4', 'S5', 'S6']:
            if slot_data[grade]:
                slot_activities.extend([f"{grade}: {activity}" for activity in slot_data[grade]])
        
        # Collect other activities
        if slot_data['otherActivities']:
            slot_activities.extend(slot_data['otherActivities'])
        
        # Only add slot to activities if there are activities
        if slot_activities:
            activities[slot_name] = slot_activities
    
    # Return message if no activities found
    if not activities:
        return {'message': f"No activities scheduled on {date_str}"}
    
    return activities