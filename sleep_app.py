import requests
import pandas as pd
import datetime
import os

# -------------------------------
# Data Collection Functions
# -------------------------------

def get_coordinates_from_zip(zipcode):
    """Get latitude and longitude from US ZIP code using Zippopotam.us API."""
    url = f"http://api.zippopotam.us/us/{zipcode}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise ValueError(f"ZIP lookup failed: {e}")
    data = r.json()
    lat = float(data['places'][0]['latitude'])
    lon = float(data['places'][0]['longitude'])
    return lat, lon


def get_weather_station(lat, lon):
    """Get nearest weather location from weather.gov API."""
    url = f"https://api.weather.gov/points/{lat},{lon}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Weather station lookup failed: {e}")
    data = r.json()
    return data["properties"]["observationStations"]


def get_hourly_weather(stations_url):
    """Get hourly observations from the nearest weather station."""
    try:
        r = requests.get(stations_url, timeout=10)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Station request failed: {e}")
    stations_data = r.json()
    if not stations_data["features"]:
        raise ValueError("No weather stations found nearby.")
    
    station_id = stations_data["features"][0]["properties"]["stationIdentifier"]
    obs_url = f"https://api.weather.gov/stations/{station_id}/observations"
    try:
        r_obs = requests.get(obs_url, timeout=10)
        r_obs.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Observation request failed: {e}")
    return r_obs.json()["features"]


def filter_nighttime_data(observations, start_hour=21, end_hour=6, tz_offset=-4):
    """Extract average values from 9 PM to 6 AM."""
    temps, humidity, pressure, wind = [], [], [], []

    for obs in observations:
        ts_utc = datetime.datetime.fromisoformat(
            obs["properties"]["timestamp"].replace("Z", "+00:00")
        )
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
# User Input & Storage
# -------------------------------

def collect_user_data_streamlit(st):
    """Collect daily self-reported data from Streamlit form."""
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

    return submitted, {
        "stress_level": stress,
        "caffeine_cups": caffeine,
        "alcohol_before_bed": alcohol,
        "screen_time_before_bed": screen_time,
        "physical_activity": physical_activity,
        "medication_usage": medication,
        "dinner_time": dinner_time,
        "satiety_level": satiety,
        "sleep_quality": sleep_quality,
    }


def save_record(record, filename="sleep_data.csv"):
    """Save record to CSV (with headers guaranteed)."""
    write_header = not os.path.exists(filename) or os.path.getsize(filename) == 0
    df = pd.DataFrame([record])
    df.to_csv(filename, mode="a", index=False, header=write_header)
    print(f"Data saved to {filename}")


# -------------------------------
# Streamlit Mode
# -------------------------------

if __name__ == "__main__":
    import sys
    if "streamlit" in sys.argv:
        import streamlit as st
        st.title("Sleep and Weather Logger")

        zipcode = st.text_input("Enter ZIP code (US)")
        if st.button("Fetch Weather"):
            if not zipcode:
                st.error("Please enter a ZIP code first.")
            else:
                try:
                    lat, lon = get_coordinates_from_zip(zipcode)
                    stations_url = get_weather_station(lat, lon)
                    observations = get_hourly_weather(stations_url)
                    weather_avg = filter_nighttime_data(observations)

                    if not weather_avg:
                        st.error("No nighttime weather data available.")
                        st.stop()

                    st.write("Nighttime weather summary:", weather_avg)

                    submitted, user_data = collect_user_data_streamlit(st)
                    if submitted:
                        record = {
                            "date": datetime.date.today().isoformat(),
                            "lat": lat,
                            "lon": lon,
                            **user_data,
                            **weather_avg
                        }
                        save_record(record)
                        st.success("Data saved!")
                        st.json(record)

                except Exception as e:
                    st.error(str(e))
    else:
        print("Run this app with: streamlit run sleep_app.py")
