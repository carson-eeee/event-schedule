
import requests as req

def get_weather():
    """Fetch 9-day weather forecast from Hong Kong Observatory API."""
    try:
        url = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php"
        data = "fnd"
        lang = "tc"
        response = req.get(f"{url}?dataType={data}&lang={lang}")
        n = eval(response.text)
        if not isinstance(n, dict) or 'weatherForecast' not in n:
            return ["Error: Invalid response from weather API"]
        forecast_list = [
            f"{n['weatherForecast'][i]['forecastDate']} : {n['weatherForecast'][i]['forecastWeather']}"
            for i in range(min(9, len(n['weatherForecast'])))
        ]
        return forecast_list
    except Exception:
        return ["Error: Failed to fetch weather data"]
    
print(get_weather())  # Example usage