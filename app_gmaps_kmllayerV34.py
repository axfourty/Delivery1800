import os
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from geopy.distance import geodesic
import googlemaps

st.set_page_config(layout="wide")

@st.cache_data
def cargar_datos():
    df = pd.read_excel("Direccion PDV.xlsx")
    df.columns = [c.strip().lower() for c in df.columns]
    lat_col = next((c for c in df.columns if "lat" in c), None)
    lon_col = next((c for c in df.columns if "lon" in c or "lng" in c), None)
    prov_col = next((c for c in df.columns if "provincia" in c), None)
    cant_col = next((c for c in df.columns if "cant" in c and "provincia" not in c), None)
    if not all([lat_col, lon_col, prov_col, cant_col]):
        st.error("❌ Columnas lat, lon, provincia o cantón no encontradas.")
        st.stop()
    df[prov_col] = df[prov_col].astype(str).str.title()
    df[cant_col] = df[cant_col].astype(str).str.title()
    return df, lat_col, lon_col, prov_col, cant_col

def clear_address():
    for k in ("coords_cliente", "address_sel"):
        st.session_state.pop(k, None)

def app():
    st.title("🚚 Logística de Pedidos 1800")

    # --- API Key ---
    api_key = (
        st.secrets.get("GOOGLE_API_KEY")
        or st.secrets.get("GOOGLE_MAPS_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_MAPS_API_KEY")
    )
    if not api_key:
        st.sidebar.error("❌ No encontré ninguna clave de Google.")
        st.stop()
    gmaps = googlemaps.Client(key=api_key)

    # --- Carga datos ---
    df, lat_c, lon_c, prov_c, cant_c = cargar_datos()
    map_kml_urls = {
        "Logistica Quito":        "https://www.google.com/maps/d/kml?mid=1VM9PYAfefV4hQRk-Ew6vBmBWKc6ol9U",
        "Logistica Guayaquil":    "https://www.google.com/maps/d/kml?mid=1tID-UCrZAom8k-CiPolZa1fqwz_02as",
        "Ubicacion PDV Nacional": "https://www.google.com/maps/d/kml?mid=1E274ysxqq1OJFObOlgGSyZ9yeD8r67k"
    }
    city_coords = {
        "Pichincha - Quito": (-0.180653, -78.467838),
        "Guayas - Guayaquil": (-2.189412, -79.889069),
        "Azuay - Cuenca":     (-2.90055,  -79.00408)
    }

    # --- Sidebar ---
    with st.sidebar:
        st.header("🔧 Filtros de Ubicación")
        if st.button("🔄 Nueva búsqueda"):
            for key in [
                "origen_pdv","transfer_exist","transfer1_pdv",
                "transfer2_exist","transfer2_pdv",
                "address_input","address_sel","coords_cliente",
                "provincia_canton","distance_limit",
                "map_logistica_Quito","map_logistica_Guayaquil","pdv_nacional"
            ]:
                st.session_state.pop(key, None)
            if hasattr(st, "experimental_rerun"):
                st.experimental_rerun()
            else:
                return

        # Origen PDV
        opciones_pdvs = sorted(df[df["base o hub"].notna()]["nombre farmacia"].tolist())
        opciones_pdvs.insert(0, "")
        origen_sel = st.selectbox("🧭 Origen (PDV)", opciones_pdvs, key="origen_pdv")

        # Transferencias
        transfer_exist = st.checkbox("¿Existe transferencia intermedia?", key="transfer_exist")
        if transfer_exist:
            df_trans = df[
                (df[prov_c] == st.session_state.get("provincia_canton", "Pichincha - Quito").split(" - ")[0]) &
                (df[cant_c] == st.session_state.get("provincia_canton", "Pichincha - Quito").split(" - ")[1])
            ]
            opciones_transf = sorted(df_trans["nombre farmacia"].tolist())
            opciones_transf.insert(0, "")
            transfer1_sel = st.selectbox("PDV Transferencia 1", opciones_transf, key="transfer1_pdv")
            transfer2_exist = st.checkbox("¿Agregar segunda transferencia?", key="transfer2_exist")
            if transfer2_exist:
                transfer2_sel = st.selectbox("PDV Transferencia 2", opciones_transf, key="transfer2_pdv")

        # Dirección Cliente
        address_input = st.text_input(
            "📌 Dirección del Cliente",
            key="address_input",
            on_change=clear_address
        )
        coords_cliente = st.session_state.get("coords_cliente", None)
        if address_input and not coords_cliente:
            preds = gmaps.places_autocomplete(address_input, components={"country": "ec"})
            opts = [p["description"] for p in preds]
            if opts:
                address_sel = st.selectbox("Sugerencias de dirección", opts, key="address_sel")
                pid = next(p["place_id"] for p in preds if p["description"] == address_sel)
                det = gmaps.place(place_id=pid)
                loc = det["result"]["geometry"]["location"]
                coords_cliente = (loc["lat"], loc["lng"])
                st.session_state["coords_cliente"] = coords_cliente

        # Provincia - Cantón
        prov_can = st.selectbox(
            "Provincia - Cantón",
            ["Pichincha - Quito","Guayas - Guayaquil","Azuay - Cuenca"],
            index=0, key="provincia_canton"
        )
        prov_sel, cant_sel = prov_can.split(" - ")

        # Distancia límite
        distance_limit = st.slider(
            "📏 Distancia máxima (km)", 0.5, 10.0, 5.0, step=0.5, key="distance_limit"
        )

        st.markdown("---")
        st.subheader("Mapas de Logística")
        # PDV Nacional primero
        pdv_nacional = st.checkbox("Mostrar Ubicación PDV Nacional", value=True, key="pdv_nacional")
        rutas_logistica = ["Logistica Quito","Logistica Guayaquil"]
        selected_logistica = [
            nm for nm in rutas_logistica
            if st.checkbox(nm, value=True, key=f"map_logistica_{nm.split()[-1]}")
        ]

    # --- Coordenadas de origen/destino/transferencias ---
    coords_o = None
    if origen_sel:
        row_o = df[df["nombre farmacia"] == origen_sel].iloc[0]
        coords_o = (row_o[lat_c], row_o[lon_c])
    coords_d = st.session_state.get("coords_cliente", None)

    coords_t1 = None
    if st.session_state.get("transfer_exist") and st.session_state.get("transfer1_pdv"):
        row = df[df["nombre farmacia"] == st.session_state["transfer1_pdv"]].iloc[0]
        coords_t1 = (row[lat_c], row[lon_c])
    coords_t2 = None
    if st.session_state.get("transfer2_exist") and st.session_state.get("transfer2_pdv"):
        row = df[df["nombre farmacia"] == st.session_state["transfer2_pdv"]].iloc[0]
        coords_t2 = (row[lat_c], row[lon_c])

    # --- Farmacias cercanas (distancia desde origen) ---
    if coords_o and coords_d:
        df_sel = df[(df[prov_c]==prov_sel)&(df[cant_c]==cant_sel)].copy()
        df_sel["distancia_km"] = [
            geodesic(coords_o, (r[lat_c], r[lon_c])).km
            for _, r in df_sel.iterrows()
        ]
        df_sel = df_sel[df_sel["distancia_km"] <= distance_limit].sort_values("distancia_km")
        if df_sel.empty:
            st.warning("⚠️ No hay farmacias cercanas.")
        else:
            st.subheader(f"✅ Farmacias dentro de {distance_limit} km en {cant_sel}, {prov_sel}")
            mostrar = [
                "base o hub","nombre farmacia","distancia_km",
                "extensión farmacia","celular punto de venta","cantón",
                "parroquia","dirección farmacia","tipo farmacia",
                "horario apertura-cierre lunes-viernes",
                "horario apertura-cierre sábado",
                "horario apertura-cierre domingo",
                "horario apertura-cierre festivos","estado farmacia"
            ]
            df_show = df_sel[mostrar].copy().rename(columns={
                "base o hub":"Base o Hub","nombre farmacia":"Nombre Farmacia",
                "distancia_km":"Distancia (km)","extensión farmacia":"Extensión Farmacia",
                "celular punto de venta":"Celular Punto de venta","cantón":"Cantón",
                "parroquia":"Parroquia","dirección farmacia":"Dirección Farmacia",
                "tipo farmacia":"Tipo Farmacia",
                "horario apertura-cierre lunes-viernes":"Horario Apertura-Cierre Lunes-Viernes",
                "horario apertura-cierre sábado":"Horario Apertura-Cierre Sábado",
                "horario apertura-cierre domingo":"Horario Apertura-Cierre Domingo",
                "horario apertura-cierre festivos":"Horario Apertura-Cierre Festivos",
                "estado farmacia":"Estado Farmacia"
            })
            st.dataframe(df_show, height=200, use_container_width=True)

    # --- Calcular ruta y segmentar distancias ---
    waypoints = []
    if coords_t1:
        waypoints.append(f"{coords_t1[0]},{coords_t1[1]}")
    if coords_t2:
        waypoints.append(f"{coords_t2[0]},{coords_t2[1]}")

    route_js = ""
    bounds_js = ""
    if coords_o and coords_d:
        # Solicitud a Directions API
        if waypoints:
            ruta = gmaps.directions(
                origin=f"{coords_o[0]},{coords_o[1]}",
                destination=f"{coords_d[0]},{coords_d[1]}",
                mode="driving",
                waypoints=waypoints
            )
        else:
            ruta = gmaps.directions(
                origin=f"{coords_o[0]},{coords_o[1]}",
                destination=f"{coords_d[0]},{coords_d[1]}",
                mode="driving"
            )
        # Segmentación de distancias
        if ruta:
            legs = ruta[0]["legs"]
            dist_vals = [leg["distance"]["value"] for leg in legs]
            dist_total_km = sum(dist_vals) / 1000
            dist_total_text = f"{dist_total_km:.2f} km"
            num_t = len(waypoints)
            if num_t > 0:
                dist_trans_km = sum(dist_vals[:num_t]) / 1000
                dist_trans_text = f"{dist_trans_km:.2f} km"
            else:
                dist_trans_text = dist_total_text
            # Mostrar con tamaño 150%
            st.markdown(
                f"<div style='font-size:150%;'>"
                f"<strong>Distancia origen → cliente:</strong> {dist_total_text} &nbsp;&nbsp;"
                f"<strong>Origen → último PDV transf.:</strong> {dist_trans_text}"
                f"</div>",
                unsafe_allow_html=True
            )
            # Preparar polyline
            encoded_pl = json.dumps(ruta[0]["overview_polyline"]["points"])
            route_js = f"""
              const decoded = google.maps.geometry.encoding.decodePath({encoded_pl});
              new google.maps.Polyline({{
                path: decoded,
                geodesic: true,
                strokeColor: "#FF0000",
                strokeWeight: 4
              }}).setMap(map);
            """
            # Ajustar viewport
            bounds_js = f"""
              const b = new google.maps.LatLngBounds();
              b.extend(new google.maps.LatLng({coords_o[0]},{coords_o[1]}));
              b.extend(new google.maps.LatLng({coords_d[0]},{coords_d[1]}));
              map.fitBounds(b);
            """

    # --- Centro y zoom para el mapa ---
    if coords_d:
        cx, cy = coords_d
    elif coords_o:
        cx, cy = coords_o
    else:
        cx, cy = city_coords[prov_can]
    zoom = 15 if distance_limit <=1 else (14 if distance_limit<=2.5 else (13 if distance_limit<=5 else 12))

    # --- Preparar hubs/origin para JS ---
    hubs = df[df["base o hub"].notna()][[lat_c, lon_c]].to_dict(orient="records")
    hubs_js = json.dumps([{"lat": h[lat_c], "lng": h[lon_c]} for h in hubs])
    origin_js = json.dumps({"lat": cx, "lng": cy}) if coords_o else "null"

    # --- Construir capas KML ---
    kml_js = ""
    for nm in selected_logistica:
        kml_js += f"new google.maps.KmlLayer({{url:'{map_kml_urls[nm]}',map:map,preserveViewport:true}});"
    if pdv_nacional:
        kml_js += f"new google.maps.KmlLayer({{url:'{map_kml_urls['Ubicacion PDV Nacional']}',map:map,preserveViewport:true}});"

    # --- HTML + JS del mapa ---
    map_html = f"""
    <div id="map" style="height:650px;width:100%;"></div>
    <script>
      function initMap() {{
        const map = new google.maps.Map(document.getElementById("map"), {{
          center: {{lat:{cx},lng:{cy}}}, zoom:{zoom}
        }});
        // Hubs (no clickable)
        const hubs = {hubs_js};
        hubs.forEach(pt => new google.maps.Marker({{
          position: pt, map,
          clickable: false,
          icon: {{
            url:'http://maps.google.com/mapfiles/ms/icons/blue-dot.png',
            scaledSize:new google.maps.Size(32,32)
          }}
        }}));
        // Origen (no clickable, 64×64)
        const origin = {origin_js};
        if(origin && origin.lat) new google.maps.Marker({{
          position: origin, map, clickable: false,
          icon: {{
            url:'http://maps.google.com/mapfiles/ms/icons/red-dot.png',
            scaledSize:new google.maps.Size(64,64)
          }}
        }});
        // Ruta
        {route_js}
        // Bounds
        {bounds_js}
        // Cliente draggable (clicable, 64×64)
        var marker = new google.maps.Marker({{
          position:{{lat:{cx},lng:{cy}}},map,draggable:true,
          icon: {{
            url:'http://maps.google.com/mapfiles/ms/icons/green-dot.png',
            scaledSize:new google.maps.Size(64,64)
          }}
        }});
        var geocoder = new google.maps.Geocoder();
        marker.addListener('dragend',function(){{
          var pos = marker.getPosition();
          geocoder.geocode({{location:pos}},function(results,status){{
            if(status==='OK'&&results[0])window.parent.postMessage(
              {{newAddress:results[0].formatted_address,lat:pos.lat(),lng:pos.lng()}},
              '*'
            );
          }});
        }});
        // KML layers
        {kml_js}
      }}
    </script>
    <script async defer
      src="https://maps.googleapis.com/maps/api/js?key={api_key}&libraries=geometry,places&callback=initMap">
    </script>
    """
    components.html(map_html, height=650)

if __name__=="__main__":
    app()
