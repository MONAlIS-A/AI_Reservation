import datetime
from django.utils import timezone
from .models import Business, Appointment

def get_slots(business_id, date_str):
    """
    Queries booked slots for a specific business and date.
    """
    try:
        query_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        appointments = Appointment.objects.filter(
            business_id=business_id,
            start_time__date=query_date,
            status='confirmed'
        ).order_by('start_time')
        
        booked_slots = []
        for appt in appointments:
            booked_slots.append({
                'start': appt.start_time.strftime('%H:%M'),
                'end': appt.end_time.strftime('%H:%M'),
                'customer': appt.customer_name
            })
        return booked_slots
    except Exception as e:
        return str(e)

def is_slot_available(business_id, start_time, end_time):
    """
    Checks if a slot is available (data isolation enforced by business_id).
    """
    overlap = Appointment.objects.filter(
        business_id=business_id,
        status='confirmed',
        start_time__lt=end_time,
        end_time__gt=start_time
    ).exists()
    return not overlap

def find_next_available_slot(business_id, after_time):
    """
    Simple logic to suggest the next slot (e.g., 30 mins after the last booking on that day).
    """
    last_appt = Appointment.objects.filter(
        business_id=business_id,
        status='confirmed',
        start_time__gte=after_time
    ).order_by('end_time').last()
    
    if not last_appt:
        return after_time + datetime.timedelta(minutes=30)
    return last_appt.end_time + datetime.timedelta(minutes=10)

def book_appointment(business_id, customer_name, customer_email, service_name, start_time_str, duration_minutes=30):
    """
    Confirms booking if free.
    """
    try:
        start_time = datetime.datetime.fromisoformat(start_time_str)
        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time)
            
        end_time = start_time + datetime.timedelta(minutes=duration_minutes)
        
        if is_slot_available(business_id, start_time, end_time):
            Appointment.objects.create(
                business_id=business_id,
                customer_name=customer_name,
                customer_email=customer_email,
                service_name=service_name,
                start_time=start_time,
                end_time=end_time
            )
            return {
                "status": "success", 
                "message": f"Appointment confirmed for {customer_name} at {start_time.strftime('%Y-%m-%d %H:%M')}. Service: {service_name}"
            }
        else:
            next_slot = find_next_available_slot(business_id, start_time)
            return {
                "status": "booked", 
                "message": f"Slot already booked. Next available slot is around {next_slot.strftime('%H:%M')}",
                "suggested_time": next_slot.isoformat()
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}

def check_booking_status(email, service_name):
    """
    Check booking status by email and service name.
    """
    try:
        appt = Appointment.objects.filter(
            customer_email__iexact=email,
            service_name__icontains=service_name,
            status='confirmed'
        ).order_by('-start_time').first()
        
        if appt:
            return {
                "status": "found",
                "message": f"Booking found! {appt.customer_name} has a booking for '{appt.service_name}' at {appt.business.name} on {appt.start_time.strftime('%Y-%m-%d %H:%M')}."
            }
        return {"status": "not_found", "message": "No confirmed booking found with those details."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
