-- Regression checks for the SetuHaul baseline.
-- Source SHA-256: b8a141fbcc57434b049ef1594245dc618905ef7db30bf3d89d358af287edf6e5
do $$
declare
  actual_count bigint;
begin
  select count(*) into actual_count from public.api_logs;
  if actual_count <> 3 then
    raise exception 'api_logs row-count mismatch: expected 3, got %', actual_count;
  end if;
  select count(*) into actual_count from public.appointment_slots;
  if actual_count <> 106 then
    raise exception 'appointment_slots row-count mismatch: expected 106, got %', actual_count;
  end if;
  select count(*) into actual_count from public.appointments;
  if actual_count <> 20 then
    raise exception 'appointments row-count mismatch: expected 20, got %', actual_count;
  end if;
  select count(*) into actual_count from public.audit_logs;
  if actual_count <> 4 then
    raise exception 'audit_logs row-count mismatch: expected 4, got %', actual_count;
  end if;
  select count(*) into actual_count from public.carriers;
  if actual_count <> 4 then
    raise exception 'carriers row-count mismatch: expected 4, got %', actual_count;
  end if;
  select count(*) into actual_count from public.chat_messages;
  if actual_count <> 20 then
    raise exception 'chat_messages row-count mismatch: expected 20, got %', actual_count;
  end if;
  select count(*) into actual_count from public.chat_threads;
  if actual_count <> 12 then
    raise exception 'chat_threads row-count mismatch: expected 12, got %', actual_count;
  end if;
  select count(*) into actual_count from public.dock_status_events;
  if actual_count <> 3 then
    raise exception 'dock_status_events row-count mismatch: expected 3, got %', actual_count;
  end if;
  select count(*) into actual_count from public.docks;
  if actual_count <> 9 then
    raise exception 'docks row-count mismatch: expected 9, got %', actual_count;
  end if;
  select count(*) into actual_count from public.driver_exceptions;
  if actual_count <> 10 then
    raise exception 'driver_exceptions row-count mismatch: expected 10, got %', actual_count;
  end if;
  select count(*) into actual_count from public.drivers;
  if actual_count <> 15 then
    raise exception 'drivers row-count mismatch: expected 15, got %', actual_count;
  end if;
  select count(*) into actual_count from public.eta_updates;
  if actual_count <> 12 then
    raise exception 'eta_updates row-count mismatch: expected 12, got %', actual_count;
  end if;
  select count(*) into actual_count from public.facilities;
  if actual_count <> 2 then
    raise exception 'facilities row-count mismatch: expected 2, got %', actual_count;
  end if;
  select count(*) into actual_count from public.facility_checkins;
  if actual_count <> 5 then
    raise exception 'facility_checkins row-count mismatch: expected 5, got %', actual_count;
  end if;
  select count(*) into actual_count from public.facility_contacts;
  if actual_count <> 5 then
    raise exception 'facility_contacts row-count mismatch: expected 5, got %', actual_count;
  end if;
  select count(*) into actual_count from public.facility_rules;
  if actual_count <> 6 then
    raise exception 'facility_rules row-count mismatch: expected 6, got %', actual_count;
  end if;
  select count(*) into actual_count from public.operational_messages;
  if actual_count <> 5 then
    raise exception 'operational_messages row-count mismatch: expected 5, got %', actual_count;
  end if;
  select count(*) into actual_count from public.roles;
  if actual_count <> 8 then
    raise exception 'roles row-count mismatch: expected 8, got %', actual_count;
  end if;
  select count(*) into actual_count from public.shipments;
  if actual_count <> 21 then
    raise exception 'shipments row-count mismatch: expected 21, got %', actual_count;
  end if;
  select count(*) into actual_count from public.users;
  if actual_count <> 10 then
    raise exception 'users row-count mismatch: expected 10, got %', actual_count;
  end if;
  select count(*) into actual_count from public.vehicle_types;
  if actual_count <> 5 then
    raise exception 'vehicle_types row-count mismatch: expected 5, got %', actual_count;
  end if;
  select count(*) into actual_count from public.vehicles;
  if actual_count <> 15 then
    raise exception 'vehicles row-count mismatch: expected 15, got %', actual_count;
  end if;
  select count(*) into actual_count from public.v_latest_eta;
  if actual_count <> 21 then
    raise exception 'v_latest_eta row-count mismatch: expected 21, got %', actual_count;
  end if;
  select count(*) into actual_count from public.v_slot_availability;
  if actual_count <> 106 then
    raise exception 'v_slot_availability row-count mismatch: expected 106, got %', actual_count;
  end if;
  select count(*) into actual_count from public.v_inbound_operational_state;
  if actual_count <> 21 then
    raise exception 'v_inbound_operational_state row-count mismatch: expected 21, got %', actual_count;
  end if;
  select count(*) into actual_count from public.v_current_facility_queue;
  if actual_count <> 3 then
    raise exception 'v_current_facility_queue row-count mismatch: expected 3, got %', actual_count;
  end if;
  select count(*) into actual_count
  from public.v_slot_availability
  where availability_status = 'AVAILABLE';
  if actual_count <> 85 then
    raise exception 'AVAILABLE slot mismatch: expected 85, got %', actual_count;
  end if;
  select count(*) into actual_count
  from public.v_slot_availability
  where availability_status = 'BLOCKED';
  if actual_count <> 7 then
    raise exception 'BLOCKED slot mismatch: expected 7, got %', actual_count;
  end if;
  select count(*) into actual_count
  from public.v_slot_availability
  where availability_status = 'OCCUPIED';
  if actual_count <> 14 then
    raise exception 'OCCUPIED slot mismatch: expected 14, got %', actual_count;
  end if;
end $$;
