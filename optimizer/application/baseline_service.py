from dataclasses import dataclass

@dataclass
class MicrogridState:
    soc_pct: float  # current battery state of charge (0-100)
    diesel_on: bool  # whether diesel is currently running
    diesel_run_hours: int  # consecutive hours diesel has been running
    diesel_off_hours: int  # consecutive hours diesel has been off

def decide(site, state: MicrogridState, current_hour_load_kw: float, solar_available_kw: float):
    # Import locally to avoid early failure if domain objects aren't strictly defined yet
    from optimizer.domain.entities import DispatchDecision
    
    # 1. Serve load from solar first.
    solar_used = min(solar_available_kw, current_hour_load_kw)
    surplus = solar_available_kw - solar_used
    
    battery = site.battery
    capacity_kwh = battery.capacity_kwh
    
    current_energy_kwh = (state.soc_pct / 100.0) * capacity_kwh
    max_energy_kwh = (battery.soc_max_pct / 100.0) * capacity_kwh
    min_energy_kwh = (battery.soc_min_pct / 100.0) * capacity_kwh
    
    # 2. Any solar surplus charges battery
    remaining_capacity_to_max_soc = max(0.0, max_energy_kwh - current_energy_kwh)
    # Charge accounts for round trip efficiency when put INTO the battery?
    # Usually you charge and get less in, or you put in and it takes more.
    # The instructions say: "Apply round_trip_efficiency."
    # Let's multiply the incoming charge by round_trip_efficiency to get energy added to battery.
    charge_kw = min(surplus, battery.max_charge_kw)
    energy_added = min(charge_kw * battery.round_trip_efficiency, remaining_capacity_to_max_soc)
    actual_charge_kw = energy_added / battery.round_trip_efficiency
    
    new_energy_kwh = current_energy_kwh + energy_added
    
    # 3. Any load shortfall after solar
    shortfall = current_hour_load_kw - solar_used
    
    # 4. Discharge battery for shortfall
    available_energy_above_min_soc = max(0.0, new_energy_kwh - min_energy_kwh)
    # Discharge does not apply round_trip_efficiency (assuming applied on charge).
    discharge_kw = min(shortfall, battery.max_discharge_kw, available_energy_above_min_soc)
    
    shortfall -= discharge_kw
    new_energy_kwh -= discharge_kw
    
    battery_kw = -discharge_kw if discharge_kw > 0 else actual_charge_kw
    
    # 5. Diesel logic
    diesel = site.diesel_generator
    diesel_on = state.diesel_on
    diesel_run_hours = state.diesel_run_hours
    diesel_off_hours = state.diesel_off_hours
    
    must_run = diesel_on and diesel_run_hours < diesel.min_uptime_h
    can_start = (not diesel_on) and diesel_off_hours >= diesel.min_downtime_h
    
    diesel_kw = 0.0
    
    # If shortfall remains AND battery can't cover it, start diesel
    needs_diesel = shortfall > 1e-5
    
    if needs_diesel and (diesel_on or can_start):
        diesel_on = True
    elif diesel_on and (needs_diesel or must_run):
        diesel_on = True
    else:
        diesel_on = False
        
    if diesel_on:
        diesel_kw = max(shortfall, diesel.min_load_kw)
        diesel_kw = min(diesel_kw, diesel.max_load_kw)
        
        # update states
        diesel_run_hours += 1
        diesel_off_hours = 0
    else:
        if state.diesel_on:
            diesel_off_hours = 1
        else:
            diesel_off_hours += 1
        diesel_run_hours = 0
        
    new_soc_pct = (new_energy_kwh / capacity_kwh) * 100.0
    
    new_state = MicrogridState(
        soc_pct=new_soc_pct,
        diesel_on=diesel_on,
        diesel_run_hours=diesel_run_hours,
        diesel_off_hours=diesel_off_hours
    )
    
    decision = DispatchDecision(
        hour=0,
        solar_kw=solar_used,
        battery_kw=battery_kw,
        diesel_kw=diesel_kw,
        load_kw=current_hour_load_kw,
        diesel_on=diesel_on,
        soc_pct=new_soc_pct,
        badges=[]
    )
    
    return decision, new_state
