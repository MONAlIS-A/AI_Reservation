import psycopg2
from django.core.management.base import BaseCommand
from business.models import Business, BusinessService
from dotenv import load_dotenv
import os

load_dotenv()

class Command(BaseCommand):
    help = 'Syncs businesses and services into a single BusinessService table from external Render PostgreSQL'

    def handle(self, *args, **options):
        conn_str = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"
        
        self.stdout.write("Connecting to external database...")
        try:
            conn = psycopg2.connect(conn_str)
            cur = conn.cursor()
            
            # 1. Fetch Businesses Metadata
            self.stdout.write("Fetching business metadata...")
            query_biz = """
                SELECT id, business_name, website, description, phone, email, 
                       address, city, state, country, zip_code, logo_url, service_name
                FROM core.businesses 
                WHERE is_active = True
            """
            cur.execute(query_biz)
            ext_businesses = cur.fetchall()
            
            uuid_to_local_biz = {}
            biz_data_map = {} 
            for row in ext_businesses:
                ext_id, name, website, desc, phone, email, addr, city, state, country, zip_code, logo, s_name = row
                
                # Update/Create local Business object (still needed as a parent)
                biz, created = Business.objects.update_or_create(
                    external_uuid=ext_id,
                    defaults={
                        'name': name or "Unknown",
                        'website_url': website or "https://example.com",
                        'description': desc or ""
                    }
                )
                uuid_to_local_biz[str(ext_id)] = biz
                
                # Store business metadata to push into services later
                biz_data_map[str(ext_id)] = {
                    'biz_phone': phone,
                    'biz_email': email,
                    'biz_address': addr,
                    'biz_city': city,
                    'biz_state': state,
                    'biz_country': country,
                    'biz_zip_code': zip_code,
                    'biz_logo_url': logo,
                    'biz_service_name': s_name
                }
                self.stdout.write(f"  Processed business metadata: {name}")

            # 2. Fetch Service Images to a map
            self.stdout.write("Fetching service images...")
            cur.execute("SELECT service_id, image_url FROM core.service_images ORDER BY sort_order ASC")
            img_rows = cur.fetchall()
            service_images = {}
            for s_id, img_url in img_rows:
                if str(s_id) not in service_images:
                    service_images[str(s_id)] = img_url # Take the first one

            # 3. Fetch and Sync Services
            self.stdout.write("Syncing services into BusinessService table...")
            query_srv = """
                SELECT id, business_id, service_name, description, base_price, 
                       category, location, duration_minutes, service_type, currency,
                       max_capacity, is_popular
                FROM core.services 
                WHERE is_active = True
            """
            cur.execute(query_srv)
            ext_services = cur.fetchall()
            
            for row in ext_services:
                srv_id, biz_uuid, srv_name, srv_desc, price, cat, loc, duration, s_type, curr, capacity, popular = row
                
                local_biz = uuid_to_local_biz.get(str(biz_uuid))
                if not local_biz: continue
                
                biz_meta = biz_data_map.get(str(biz_uuid), {})
                img_url = service_images.get(str(srv_id))
                
                # Update or Create BusinessService with ALL fields
                BusinessService.objects.update_or_create(
                    business=local_biz,
                    name=srv_name,
                    defaults={
                        'description': srv_desc or "",
                        'price': f"{price} {curr or ''}" if price else "N/A",
                        'category': cat,
                        'location': loc,
                        'duration_minutes': duration,
                        'service_type': s_type,
                        'currency': curr,
                        'max_capacity': capacity,
                        'image_url': img_url,
                        'is_popular': popular or False,
                        # Adding business metadata here
                        'biz_phone': biz_meta.get('biz_phone'),
                        'biz_email': biz_meta.get('biz_email'),
                        'biz_address': biz_meta.get('biz_address'),
                        'biz_city': biz_meta.get('biz_city'),
                        'biz_state': biz_meta.get('biz_state'),
                        'biz_country': biz_meta.get('biz_country'),
                        'biz_zip_code': biz_meta.get('biz_zip_code'),
                        'biz_logo_url': biz_meta.get('biz_logo_url'),
                        'biz_service_name': biz_meta.get('biz_service_name'),
                    }
                )
                self.stdout.write(f"  Saved service: {srv_name} with all metadata")

            cur.close()
            conn.close()
            self.stdout.write(self.style.SUCCESS("Synchronization complete! All data stored in BusinessService table."))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during sync: {e}"))
