document.addEventListener("DOMContentLoaded", () => {
  const searchForm = document.getElementById("searchForm");
  const cityInput = document.getElementById("cityInput");
  const suggestionList = document.getElementById("suggestionList");
  const resultContainer = document.getElementById("resultContainer");
  const statusBar = document.getElementById("statusBar");
  const weatherTemplate = document.getElementById("weatherTemplate");
  const skeletonTemplate = document.getElementById("skeletonTemplate");
  const userForm = document.getElementById("userForm");
  const userName = document.getElementById("userName");
  const userLabel = document.getElementById("userLabel");
  const userButton = userForm.querySelector("button");

  let currentUser = null;
  try {
    currentUser = localStorage.getItem("user");
  } catch {}

  let favourites = [];
  const favouritesBox = document.getElementById("favourites");

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

    const city = data.location.split(",")[0].trim();
    showHistory(city, clone.querySelector(".js-history"));
    const star = clone.querySelector(".js-fav");
    const paintStar = () => {
      star.firstElementChild.className = isFavourite(city)
        ? "fa-solid fa-star text-warning"
        : "fa-regular fa-star";
    };
    if (currentUser) {
      star.classList.remove("d-none");
      paintStar();
      star.addEventListener("click", async () => {
        const adding = !isFavourite(city);
        const res = await fetch(
          `/api/users/${encodeURIComponent(currentUser)}/favourites/${encodeURIComponent(city)}`,
          { method: adding ? "PUT" : "DELETE" },
        );
        if (!res.ok) {
          statusBar.textContent = "Could not save the favourite.";
          return;
        }
        favourites = adding
          ? [...favourites, city]
          : favourites.filter((f) => f.toLowerCase() !== city.toLowerCase());
        paintStar();
        renderFavourites();
      });
    }

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
  function showUser() {
    userLabel.textContent = currentUser ? `Signed in as ${currentUser}` : "";
    userName.classList.toggle("d-none", Boolean(currentUser));
    userButton.textContent = currentUser ? "Sign out" : "Sign in";
    loadFavourites();
  }

  const isFavourite = (city) =>
    favourites.some((f) => f.toLowerCase() === city.toLowerCase());

  async function loadFavourites() {
    favourites = [];
    if (currentUser) {
      try {
        const url = `/api/users/${encodeURIComponent(currentUser)}/favourites`;
        let res = await fetch(url);
        if (res.status === 404) {
          // The database is wiped every night, but this browser still remembers the name.
          await fetch("/api/users", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: currentUser }),
          });
          res = await fetch(url);
        }
        if (res.ok) favourites = (await res.json()).favourites;
      } catch {}
    }
    renderFavourites();
  }

  // Snapshots MongoDB kept for this city; nothing is shown if there are none
  async function showHistory(city, line) {
    try {
      const res = await fetch(`/api/snapshots?city=${encodeURIComponent(city)}`);
      if (!res.ok) return;
      const { snapshots } = await res.json();
      if (!snapshots.length) return;
      const time = (s) =>
        new Date(s.fetched_at).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        });
      const latest = snapshots[0];
      const oldest = snapshots[snapshots.length - 1];
      if (snapshots.length === 1) {
        line.textContent = `1 snapshot saved, at ${time(latest)}.`;
        return;
      }
      const temps = snapshots
        .map((s) => s.current && s.current.temperature_2m)
        .filter(Number.isFinite);
      const count =
        snapshots.length >= 20 ? `Latest ${snapshots.length}` : snapshots.length;
      line.textContent =
        `${count} snapshots saved between ${time(oldest)} and ${time(latest)}` +
        (temps.length
          ? ` · temperature ${Math.round(Math.min(...temps))}° to ${Math.round(Math.max(...temps))}°C`
          : "");
    } catch {}
  }

  function renderFavourites() {
    favouritesBox.replaceChildren();
    for (const city of favourites) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "btn btn-sm btn-outline-secondary";
      chip.textContent = city;
      chip.addEventListener("click", () => {
        cityInput.value = city;
        searchForm.requestSubmit();
      });
      favouritesBox.appendChild(chip);
    }
  }

  async function signIn(name) {
    const res = await fetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) {
      statusBar.textContent =
        res.status === 400
          ? "Names use letters, digits, - and _ (up to 40)."
          : "Users are unavailable right now.";
      return;
    }
    currentUser = name;
    try {
      localStorage.setItem("user", name);
    } catch {}
    showUser();
  }

  userForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (currentUser) {
      currentUser = null;
      try {
        localStorage.removeItem("user");
      } catch {}
      showUser();
    } else if (userName.value.trim()) {
      await signIn(userName.value.trim());
    }
  });

  showUser();
});
