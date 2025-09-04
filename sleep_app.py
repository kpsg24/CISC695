import requests
import pandas as pd
import datetime
import os


# -------------------------------
# Data Collection Functions
# -------------------------------

def get_coordinates_from_zip(zipcode):
    """
    Get latitude and longitude from US ZIP code using Zippopotam.us API.
    """
    url = f"http://api.zippopotam.us/us/{zipcode}"
    r = requests.get(url)
    if r.status_code != 200:
        raise ValueError("Invalid ZIP code or location not found.")
    data = r.json()
    lat = float(data['places'][0]['latitude'])
    lon = float(data['places'][0]['longitude'])
    return lat, lon


def get_weather_station(lat, lon):
    """
    Get nearest weather location from weather.gov API.
    """
    url = f"https://api.weather.gov/points/{lat},{lon}"
    r = requests.get(url)
    r.raise_for_status()
    data = r.json()
    return data["properties"]["observationStations"]


def get_hourly_weather(stations_url):
    """
    Get hourly observations from the nearest weather station.
    """
    r = requests.get(stations_url)
    r.raise_for_status()
    stations_data = r.json()
    if not stations_data["features"]:
        raise ValueError("No weather stations found nearby.")
    
    station_id = stations_data["features"][0]["properties"]["stationIdentifier"]
    obs_url = f"https://api.weather.gov/stations/{station_id}/observations"
    r_obs = requests.get(obs_url)
    r_obs.raise_for_status()
    return r_obs.json()["features"]


def filter_nighttime_data(observations, start_hour=21, end_hour=6, tz_offset=-4):
    """
    Extract average values from 9 PM to 6 AM.
    tz_offset is the timezone offset from UTC.
    """
    temps = []
    humidity = []
    pressure = []
    wind = []

    for obs in observations:
        ts_utc = datetime.datetime.fromisoformat(obs["properties"]["timestamp"].replace("Z", "+00:00"))
        local_time = ts_utc + datetime.timedelta(hours=tz_offset)
        if local_time.hour >= start_hour or local_time.hour <= end_hour:
            props = obs["properties"]
            if props["temperature"] and props["temperature"]["value"] is not None:
                temps.append(props["temperature"]["value"])
            if props["relativeHumidity"] and props["relativeHumidity"]["value"] is not None:
                humidity.append(props["relativeHumidity"]["value"])
            if props["barometricPressure"] and props["barometricPressure"]["value"] is not None:
                pressure.append(props["barometricPressure"]["value"])
            if props["windSpeed"] and props["windSpeed"]["value"] is not None:
                wind.append(props["windSpeed"]["value"])

    return {
        "avg_temp_C": round(sum(temps)/len(temps), 2) if temps else None,
        "avg_humidity_percent": round(sum(humidity)/len(humidity), 2) if humidity else None,
        "avg_pressure_Pa": round(sum(pressure)/len(pressure), 2) if pressure else None,
        "avg_wind_mps": round(sum(wind)/len(wind), 2) if wind else None
    }


# -------------------------------
# NEW: Historical Weather Support
# -------------------------------

def get_historical_weather(lat, lon, date, start_hour=21, end_hour=6):
    """
    Get historical weather data from Open-Meteo Archive API for a given date.
    """
    url = (
        f"https://archive-api.open-meteo.com/v1/archive?"
        f"latitude={lat}&longitude={lon}"
        f"&start_date={date}&end_date={date}"
        f"&hourly=temperature_2m,relative_humidity_2m,pressure_msl,windspeed_10m"
    )
    r = requests.get(url)
    r.raise_for_status()
    data = r.json()

    hourly_times = data["hourly"]["time"]
    temps = data["hourly"]["temperature_2m"]
    humidity = data["hourly"]["relative_humidity_2m"]
    pressure = data["hourly"]["pressure_msl"]
    wind = data["hourly"]["windspeed_10m"]

    df = pd.DataFrame({
        "time": pd.to_datetime(hourly_times),
        "temperature_C": temps,
        "humidity_percent": humidity,
        "pressure_Pa": pressure,
        "wind_mps": wind
    })

    # Select nighttime hours
    df_night = df[(df["time"].dt.hour >= start_hour) | (df["time"].dt.hour <= end_hour)]

    return {
        "avg_temp_C": round(df_night["temperature_C"].mean(), 2),
        "avg_humidity_percent": round(df_night["humidity_percent"].mean(), 2),
        "avg_pressure_Pa": round(df_night["pressure_Pa"].mean(), 2),
        "avg_wind_mps": round(df_night["wind_mps"].mean(), 2)
    }


# -------------------------------
# User Input & Storage
# -------------------------------

def collect_user_data():
    """
    Collect daily self-reported data from user input.
    """
    stress = int(input("Stress/emotion level (1-5): "))
    caffeine = int(input("Caffeine intake (cups, 0-5+): "))
    alcohol = input("Alcohol intake before bedtime (yes/no): ").strip().lower()
    screen_time = input("Screen time before bedtime (yes/no): ").strip().lower()
    physical_activity = input("Physical activity today (yes/no): ").strip().lower()
    medication = input("Medication usage (yes/no): ").strip().lower()
    dinner_time = input("Dinner time (HH:MM, 24-hour): ").strip()
    satiety = input("Perceived satiety level (mild/moderate/full): ").strip().lower()
    sleep_quality = int(input("Sleep quality (1-5): "))
    
    return {
        "stress_level": stress,
        "caffeine_cups": caffeine,
        "alcohol_before_bed": alcohol,
        "screen_time_before_bed": screen_time,
        "physical_activity": physical_activity,
        "medication_usage": medication,
        "dinner_time": dinner_time,
        "satiety_level": satiety,
        "sleep_quality": sleep_quality
    }


def save_record(record, filename="sleep_data.csv"):
    """
    Save record to CSV.
    """
    file_exists = os.path.exists(filename)
    df = pd.DataFrame([record])
    df.to_csv(filename, mode="a", index=False, header=not file_exists)
    print(f"Data saved to {filename}")


# -------------------------------
# Main CLI
# -------------------------------

def run_cli():
    zipcode = input("Enter your ZIP code: ").strip()
    lat, lon = get_coordinates_from_zip(zipcode)

    date_input = input("Enter a past date for historical weather (YYYY-MM-DD) or leave blank for today: ").strip()
    if date_input:
        weather_avg = get_historical_weather(lat, lon, date_input)
        record_date = date_input
    else:
        stations_url = get_weather_station(lat, lon)
        observations = get_hourly_weather(stations_url)
        weather_avg = filter_nighttime_data(observations)
        record_date = datetime.date.today().isoformat()

    if not weather_avg:
        print("No nighttime weather data available.")
        return

    user_data = collect_user_data()
    record = {"date": record_date, "lat": lat, "lon": lon, **user_data, **weather_avg}
    save_record(record)
    print(record)


# -------------------------------
# Streamlit Mode
# -------------------------------

if __name__ == "__main__":
    import sys
    if "streamlit" in sys.argv:
        import streamlit as st
        st.title("Sleep and Weather Logger")

        zipcode = st.text_input("Enter ZIP code (US)")
        date_input = st.text_input("Enter a past date (YYYY-MM-DD) or leave blank for today")

        if st.button("Fetch and Record"):
            try:
                lat, lon = get_coordinates_from_zip(zipcode)

                if date_input:
                    weather_avg = get_historical_weather(lat, lon, date_input)
                    record_date = date_input
                else:
                    stations_url = get_weather_station(lat, lon)
                    observations = get_hourly_weather(stations_url)
                    weather_avg = filter_nighttime_data(observations)
                    record_date = datetime.date.today().isoformat()

                if not weather_avg:
                    st.error("No nighttime weather data available.")
                    st.stop()

                st.write("Nighttime weather summary:", weather_avg)

                with st.form("user_data_form"):
                    stress = st.slider("Stress/emotion level", 1, 5, 3)
                    caffeine = st.number_input("Caffeine intake (cups)", min_value=0, max_value=10, value=0)
                    alcohol = st.selectbox("Alcohol intake before bedtime", ["no", "yes"])
                    screen_time = st.selectbox("Screen time before bedtime", ["no", "yes"])
                    physical_activity = st.selectbox("Physical activity today", ["no", "yes"])
                    medication = st.selectbox("Medication usage", ["no", "yes"])
                    dinner_time = st.text_input("Dinner time (HH:MM)")
                    satiety = st.selectbox("Perceived satiety level", ["mild", "moderate", "full"])
                    sleep_quality = st.slider("Sleep quality", 1, 5, 3)
                    submitted = st.form_submit_button("Save Record")

                    if submitted:
                        record = {
                            "date": record_date,
                            "lat": lat,
                            "lon": lon,
                            "stress_level": stress,
                            "caffeine_cups": caffeine,
                            "alcohol_before_bed": alcohol,
                            "screen_time_before_bed": screen_time,
                            "physical_activity": physical_activity,
                            "medication_usage": medication,
                            "dinner_time": dinner_time,
                            "satiety_level": satiety,
                            "sleep_quality": sleep_quality,
                            **weather_avg
                        }
                        save_record(record)
                        st.success("Data saved!")
                        st.json(record)
            except Exception as e:
                st.error(str(e))
    else:
        run_cli()
