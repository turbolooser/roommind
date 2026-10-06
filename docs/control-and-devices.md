# Control And Device Guide

This page explains RoomMind's control settings and related device options.

## What Priority Does

In `Settings -> Control -> Priority`, the slider balances comfort against runtime/energy use for MPC.

- Toward `Comfort`: RoomMind reacts earlier and works harder to stay close to the target temperature.
- Toward `Efficiency`: RoomMind allows more drift around the target to reduce heating/cooling runtime.

This setting does **not** change your schedule targets, overrides, comfort temperature, or eco temperature. It only changes how aggressively MPC tries to reach and hold those targets.

## Thermostat vs Climate Device

Both options are Home Assistant `climate.*` entities, but RoomMind treats them differently:

- `Thermostat`: a radiator thermostat / TRV style device.
- `Climate Device`: an AC, heat pump, or other climate entity used for cooling or forced-air heating.

In practice:

- Choose `Thermostat` for radiator valves and similar heating-only valve devices.
- Choose `Climate Device` for ACs, minisplits, heat pumps, and other self-contained HVAC units.

## Full Control vs Managed

An external room temperature sensor is the key split:

- `Full Control`: RoomMind uses the external sensor as the room truth and can actively shape device output.
- `Managed`: without an external room sensor, RoomMind sends target temperatures but the device mostly regulates itself using its own internal sensor.

This matters for the options below.

## Setpoint Mode: Proportional vs Direct

`Setpoint mode` is relevant for thermostat/TRV devices in `Full Control` rooms.

### Proportional

RoomMind calculates the required heating power, then sends a boosted device setpoint to achieve roughly that output.

Example:

- room target is `21°C`
- more heat is needed
- RoomMind may send `26-28°C` to the TRV to force the valve open harder

Best for:

- radiator valves / TRVs
- devices that need an exaggerated setpoint to actually deliver heat

### Direct

RoomMind sends the real target temperature and lets the device regulate itself.

Best for:

- space heaters
- pellet stoves
- devices with their own thermostat logic that should stay in control internally

#### Setpoint offset

Some devices measure the room differently than your room sensor, for example an AC mounted near the floor that cools its own sensor. With `Direct` and an external room sensor you can set a `Setpoint offset` (-5 to +5 °C, step 0.5, default 0). It is added to the room target before the target is sent to the device, for heating and cooling alike.

- Device reads **colder** than the room: use a **negative** value.
- Device reads **warmer** than the room: use a **positive** value.

Example: the room target is 24°C. While cooling, the device thinks the room is 2° colder than it is and switches off too early. Set the offset to `-2`: the device receives 22°C and keeps running until the room is really at 24°C.

The offset is applied before the device limits (`min_temp`/`max_temp`) and the step rounding, and it is kept for the `Setback` idle action. It has no effect in `Proportional` mode. The field is only offered in rooms with an external room sensor, because Managed rooms have no reference to correct against; an old value stays ignored there. On Fahrenheit systems the field is shown in °F.

#### Upper device limit

In `Proportional` mode the boosted heating setpoint stays one step (`target_temp_step`, 0.5 °C if the device reports none) below the device's `max_temp`, and never below the room target. Some integrations reject exactly their own `max_temp`, which made the Dyson Heat/Cool purifier ignore the 37°C setpoint. The cooling floor (`min_temp`) is unchanged.

## Idle Behavior: Off, Fan Only, Setback

`When idle` applies to `Climate Device` entries.

### Turn off

RoomMind turns the device off, or falls back to the device's minimum/off-like behavior if true off is not supported.

### Fan only

RoomMind keeps the device running in fan mode without active heating/cooling.

Useful when you want:

- air circulation
- less harsh on/off transitions

### Setback

RoomMind keeps the current HVAC mode active, but moves the target away from the room target:

- heating setback = `heat target - 2°C`
- cooling setback = `cool target + 2°C`

This lets the device back off instead of shutting off completely.

### The setback offset

The offset defaults to `2 K` and is configurable at two levels:

- **globally** in the integration's options flow (`Idle setback offset`)
- **per device** in `Devices` → `Set back by (K)`, shown once `When idle` is set to
  `Setback`. Leave it empty to inherit the global value.

The per-device level exists because the useful offset follows the device type, not
the room. An AC reacts within seconds, so `2 K` is fine. A radiator is sluggish, and
`2 K` lets the room fall a full degree below target before heat returns — `1 K` is
the practical value there. A room with both device types needs both offsets at the
same time, which a single global or per-room value cannot express.

Existing configurations keep working unchanged: a device without its own value
inherits the global setting, and no migration is required.

## Idle Behavior for Thermostats: Off, Low, Setback

`When idle` also applies to `Thermostat` / TRV entries, with different options.

### Turn off

RoomMind sends the TRV to its `off` state.

### Low

RoomMind keeps the TRV in its current heating mode but lowers the setpoint to the device's minimum temperature.

Useful for battery-powered Zigbee TRVs that enter deep sleep when set to `off` and then stop reacting to commands. `Low` keeps the valve responsive while effectively stopping heating.

### Setback

RoomMind keeps the valve in heating mode and lowers the setpoint to `heat target - offset`
instead of driving it to the device minimum.

Useful for **sluggish radiators**. With `Low` the valve closes completely, the radiator
goes cold, and after reopening it takes minutes before heat actually reaches the room —
the room keeps falling during that time. In one measured case (bathroom radiator,
20 hours of valid measurement) the room gained `+0.01 K/h`, i.e. it stood still. With
`Setback` the radiator stays lukewarm and responds immediately.

The offset follows the same global/per-device rules as for climate devices
(see [The setback offset](#the-setback-offset)); `1 K` is the practical value for a
radiator.

### Which one to choose

| Situation | Use |
|---|---|
| Battery Zigbee TRV that stops reacting after being off (deep sleep) | `Low` |
| Sluggish radiator that takes minutes to deliver heat again | `Setback` |
| Valve should genuinely stop, reaction time does not matter | `Turn off` |

`Low` remains the default and stays the right answer for deep-sleep-prone valves:
it keeps the device awake while stopping all heat output. `Setback` keeps *some*
heat in the radiator, so it costs a little energy in exchange for response time.

### Interaction with staged idle

`Idle off after minutes` (integration options) escalates a continuous setback to a
full turn-off once the timer expires — the valve then goes to `off`, which **undoes
what setback is for**. Three things to know:

- **`0` (the default) disables the escalation entirely.** The setback then holds for
  as long as the room stays idle, which is exactly what a sluggish radiator wants.
- A value `> 0` turns the valve off after that many minutes of continuous setback.
  Observed in practice: with `30`, a bathroom TRV held its setback setpoint from
  19:28 and was switched off at 19:58 — the radiator then cooled down anyway.
- The timer resets whenever the device is commanded back into an active mode, so a
  room that actually heats now and then never reaches the escalation.

Note that `idle_off_after_minutes` is a **global** setting. A single value has to
suit both your ACs (where escalating to off is often wanted) and your radiators
(where it defeats the purpose), so pick it for whichever matters more in your
setup.

Note that escalation sends the valve to `off` regardless of the deep-sleep concern
behind `Low`. On a battery TRV prone to deep sleep, prefer `Low`, or keep the
escalation disabled.

## Evaporator Drying

`Settings -> Evaporator drying` (with a per-device override in `Devices`) keeps an AC's indoor fan running for a while after cooling stops, before the unit really switches off.

Drying the evaporator coil this way cuts down on biofilm buildup and a musty smell on the next cooling start. It is off by default.

### Turning it on

- Enable it globally in `Settings -> Evaporator drying`.
- Or override a single device in `Devices`: `Use global setting`, `Always on`, or `Always off`. Only `Climate Device` / AC entries offer this; TRVs have no evaporator coil.

Drying time, the minimum cooling time before a run is worth it, an optional drain delay, drying mode (`fan_only` or `dry`), and fan speed are all configurable, both globally and per device. A device left on its default values falls back to the global setting.

### While it runs

- A returning cooling demand cancels the run immediately and the AC goes straight back to cooling.
- A returning heating demand cancels it too, and resets the tracked wetness for that room's ACs.
- A running or draining device shows a badge with the remaining time on the room's status.

### Relation to `When idle`

If a drain delay is configured, a run normally holds the device off first so condensate can drain, then switches to the fan. With `When idle` set to `Setback` the device is never actually off, so the drain step is skipped and the run starts directly in the fan phase.

### Relation to an explicit shutdown

An explicit shutdown, `Action when schedule is off` or `Action when away` set to `Turn off devices`, overrides `When idle` (described in the next section) so a device cannot stay fanning or set back indefinitely. Evaporator drying is different: an explicit shutdown does not block it. A run can start fresh or keep going, and always finishes normally, before the device goes off.

## When "Turn off devices" Overrides `When idle`

`When idle` describes what a device should do while the room simply has no heating or cooling demand. It does **not** apply when you explicitly shut a room down via:

- `Settings → Control → Action when schedule is off` set to `Turn off devices`
- `Settings → Presence → Action when away` set to `Turn off devices`

In those cases RoomMind turns the devices off even if `When idle` is set to `Fan only` or `Setback`. Otherwise an AC would keep circulating air after the schedule ended.

The single exception is `Low` on thermostats: it stays active because the affected TRVs stop responding after being set to `off`. Lowering the setpoint to the device minimum already stops all heat output.

## Smart Source Selection

`Smart source selection` only appears when a room has:

- at least one `Thermostat` / TRV
- at least one `Climate Device` / AC
- an external temperature sensor

In that case RoomMind can decide which source should heat:

- TRV / boiler side
- AC / heat pump side
- or both, when the gap is large

It uses temperature gap and outdoor conditions to make that choice.
