document.addEventListener("DOMContentLoaded", () => {
  const searchForm = document.getElementById("searchForm");
  const cityInput = document.getElementById("cityInput");
  const suggestionList = document.getElementById("suggestionList");
  const resultContainer = document.getElementById("resultContainer");
  const statusBar = document.getElementById("statusBar");
  const weatherTemplate = document.getElementById("weatherTemplate");
  const skeletonTemplate = document.getElementById("skeletonTemplate");

  // Weather code mapping to FontAwesome icons & descriptions
  function getWeatherDetails(code) {
    const codes = {
      0: { text: "Clear sky", icon: "fa-sun text-warning" },
      1: { text: "Mainly clear", icon: "fa-cloud-sun text-warning" },
      2: { text: "Partly cloudy", icon: "fa-cloud-sun text-secondary" },
      3: { text: "Overcast", icon: "fa-cloud text-secondary" },
      45: { text: "Foggy", icon: "fa-smog text-muted" },
      51: { text: "Light drizzle", icon: "fa-cloud-rain text-info" },
      61: { text: "Rain", icon: "fa-cloud-showers-heavy text-primary" },
      71: { text: "Snow", icon: "fa-snowflake text-info" },
      95: { text: "Thunderstorm", icon: "fa-bolt text-warning" },
    };
    return codes[code] || { text: "Fair", icon: "fa-cloud text-secondary" };
  }

  // Live City Autocomplete
  let debounceTimer;
  cityInput.addEventListener("input", (e) => {
    clearTimeout(debounceTimer);
    const query = e.target.value.trim();
    if (query.length < 2) {
      suggestionList.innerHTML = "";
      return;
    }
    debounceTimer = setTimeout(async () => {
      try {
        const res = await fetch(
          `https://geocoding-api.open-meteo.com/v1/search?name=${query}&count=5`,
        );
        const data = await res.json();
        suggestionList.innerHTML = "";
        if (data.results) {
          data.results.forEach((loc) => {
            const option = document.createElement("option");
            option.value = `${loc.name}, ${loc.country || ""}`;
            suggestionList.appendChild(option);
          });
        }
      } catch (err) {
        console.error("Autocomplete error:", err);
      }
    }, 300);
  });

  // Form Submit Handler
  searchForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const cityName = cityInput.value.split(",")[0].trim();
    if (!cityName) return;

    // Show skeleton loader
    resultContainer.innerHTML = "";
    resultContainer.appendChild(skeletonTemplate.content.cloneNode(true));
    statusBar.textContent = `Fetching forecast for ${cityName}...`;

    try {
      const res = await fetch(
        `/api/weather?city=${encodeURIComponent(cityName)}`,
      );
      if (!res.ok) throw new Error("City not found");
      const data = await res.json();

      renderWeather(data);
      statusBar.textContent = `Successfully loaded forecast for ${data.location}.`;
    } catch (err) {
      resultContainer.innerHTML = `<div class="alert alert-danger text-center" role="alert">Could not find weather data for "${cityName}". Please try another city.</div>`;
      statusBar.textContent = "Error loading weather.";
    }
  });

  function renderWeather(data) {
    resultContainer.innerHTML = "";
    const clone = weatherTemplate.content.cloneNode(true);

    clone.querySelector(".js-city-name").textContent = data.location;

    const current = data.current;
    const currentDetails = getWeatherDetails(current.weather_code);

    clone.querySelector(".js-today-max").textContent =
      `${Math.round(current.temperature_2m)}°C`;
    clone.querySelector(".js-today-min").textContent = currentDetails.text;
    clone.querySelector(".js-today-humidity").textContent =
      `${current.relative_humidity_2m}% Humidity`;

    // Render 5-day upcoming forecast
    const upcomingContainer = clone.querySelector(".js-upcoming");
    const daily = data.daily;

    for (let i = 1; i < 6 && i < daily.time.length; i++) {
      const dateStr = new Date(daily.time[i]).toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
      const details = getWeatherDetails(daily.weather_code[i]);

      const col = document.createElement("div");
      col.className = "col";
      col.innerHTML = `
                <div class="card h-100 border-0 shadow-sm p-3 text-center bg-body-tertiary">
                    <p class="text-muted small fw-bold mb-2">${dateStr}</p>
                    <div class="my-2"><i class="fa-solid ${details.icon} fa-2x"></i></div>
                    <p class="fw-bold mb-1">${Math.round(daily.temperature_2m_max[i])}° <span class="text-muted fw-normal">${Math.round(daily.temperature_2m_min[i])}°</span></p>
                    <small class="text-muted" style="font-size: 0.75rem;">${details.text}</small>
                </div>
            `;
      upcomingContainer.appendChild(col);
    }

    resultContainer.appendChild(clone);
  }
});
