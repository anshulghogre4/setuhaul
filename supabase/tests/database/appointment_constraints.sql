-- Verify that PostgreSQL remains the final concurrency authority for bookings.
-- Each expected unique violation rolls back its inner subtransaction.

do $$
declare
  violated_object text;
begin
  begin
    insert into public.appointments (
      appointment_id,
      shipment_id,
      slot_id,
      appointment_status,
      booking_source,
      is_current,
      booked_at,
      updated_at
    ) values (
      'APT-CONSTRAINT-SLOT',
      'SHP1020',
      'SLOT-JAI-015',
      'CONFIRMED',
      'SCHEDULING_TOOL',
      1,
      '2026-08-04T10:00:00+05:30',
      '2026-08-04T10:00:00+05:30'
    );
    raise exception 'Duplicate active appointment per slot was accepted';
  exception
    when unique_violation then
      get stacked diagnostics violated_object = constraint_name;
      if violated_object <> 'ux_active_appointment_per_slot' then
        raise exception 'Unexpected unique violation: %', violated_object;
      end if;
  end;

  begin
    insert into public.appointments (
      appointment_id,
      shipment_id,
      slot_id,
      appointment_status,
      booking_source,
      is_current,
      booked_at,
      updated_at
    ) values (
      'APT-CONSTRAINT-SHIPMENT',
      'SHP1002',
      'SLOT-GGN-080',
      'CONFIRMED',
      'SCHEDULING_TOOL',
      1,
      '2026-08-04T10:00:00+05:30',
      '2026-08-04T10:00:00+05:30'
    );
    raise exception 'Duplicate current active appointment per shipment was accepted';
  exception
    when unique_violation then
      get stacked diagnostics violated_object = constraint_name;
      if violated_object <> 'ux_current_active_appointment_per_shipment' then
        raise exception 'Unexpected unique violation: %', violated_object;
      end if;
  end;
end $$;
