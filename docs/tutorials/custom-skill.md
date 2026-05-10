# Develop a Skill

This tutorial shows how to create, test, and install a custom skill for Cognix.

## What is a Skill?

A skill is a reusable capability that agents can use. It consists of:

- `skill.yaml` — Manifest with metadata, tool definitions, and config schema
- `handler.py` — Python entrypoint with the actual implementation

## Step 1: Create the Skill Scaffold

```bash
cognix skill create weather-skill
cd weather-skill
```

This creates:

```
weather-skill/
├── skill.yaml
├── handler.py
└── requirements.txt
```

## Step 2: Define the Manifest

Edit `skill.yaml`:

```yaml
name: weather-skill
version: 0.1.0
description: Get current weather and forecasts for any location
author: you
tags: [weather, api, location]

tools:
  - name: get_weather
    description: Get current weather for a location
    parameters:
      type: object
      properties:
        location:
          type: string
          description: City name or coordinates (e.g., "Singapore" or "1.3521,103.8198")
        units:
          type: string
          enum: [celsius, fahrenheit]
          description: Temperature units
          default: celsius
      required: [location]

  - name: get_forecast
    description: Get 5-day weather forecast
    parameters:
      type: object
      properties:
        location:
          type: string
          description: City name or coordinates
      required: [location]

config:
  api_key:
    type: string
    description: OpenWeatherMap API key
    required: true
```

## Step 3: Implement the Handler

Edit `handler.py`:

```python
"""Weather skill handler."""

import httpx


async def get_weather(location: str, units: str = "celsius", config: dict = None) -> str:
    """Get current weather for a location."""
    api_key = config.get("api_key", "")
    unit_param = "metric" if units == "celsius" else "imperial"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "q": location,
                "appid": api_key,
                "units": unit_param,
            },
        )
        data = response.json()
    
    if response.status_code != 200:
        return f"Error: {data.get('message', 'Unknown error')}"
    
    temp = data["main"]["temp"]
    feels_like = data["main"]["feels_like"]
    description = data["weather"][0]["description"]
    humidity = data["main"]["humidity"]
    wind_speed = data["wind"]["speed"]
    
    unit_symbol = "°C" if units == "celsius" else "°F"
    
    return (
        f"Weather in {data['name']}:\n"
        f"- Condition: {description}\n"
        f"- Temperature: {temp}{unit_symbol} (feels like {feels_like}{unit_symbol})\n"
        f"- Humidity: {humidity}%\n"
        f"- Wind: {wind_speed} m/s"
    )


async def get_forecast(location: str, config: dict = None) -> str:
    """Get 5-day weather forecast."""
    api_key = config.get("api_key", "")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "q": location,
                "appid": api_key,
                "units": "metric",
            },
        )
        data = response.json()
    
    if response.status_code != 200:
        return f"Error: {data.get('message', 'Unknown error')}"
    
    forecasts = []
    for item in data["list"][:5]:
        dt = item["dt_txt"]
        temp = item["main"]["temp"]
        desc = item["weather"][0]["description"]
        forecasts.append(f"- {dt}: {temp}°C, {desc}")
    
    return f"5-day forecast for {data['city']['name']}:\n" + "\n".join(forecasts)
```

## Step 4: Add Dependencies

Edit `requirements.txt`:

```
httpx>=0.27
```

## Step 5: Test Locally

```bash
# Install the skill
cognix skill install .

# Verify it's installed
cognix skill list

# Search for it
cognix skill search "weather"
```

## Step 6: Use the Skill

Once installed, agents can use the skill's tools:

=== "CLI"

    ```bash
    cognix agent chat my-agent "What's the weather in Singapore?"
    ```

    The agent will automatically use the `get_weather` tool.

=== "API"

    The agent's LLM will detect when to use the tool based on the conversation context.

## Skill Configuration

Users configure skills when they install them:

```bash
cognix skill install weather-skill --config '{"api_key": "your-openweathermap-key"}'
```

Or via the API:

```bash
curl -X POST http://localhost:8000/api/v1/skills/install \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "weather-skill",
    "config": {"api_key": "your-openweathermap-key"}
  }'
```

## Best Practices

1. **Clear descriptions** — Help the LLM understand when to use each tool
2. **Parameter validation** — Use JSON Schema to define required/optional params
3. **Error handling** — Return helpful error messages, not stack traces
4. **Idempotency** — Tools should be safe to retry
5. **Config separation** — Keep secrets in config, not in code

## Next Steps

- [Deploy to Production](deployment.md) — Deploy your skills and agents
- [Skills System Guide](../guides/skills.md) — Advanced skill features
