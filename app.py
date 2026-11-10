import streamlit as st
import pandas as pd
from io import BytesIO
import re
import unicodedata

st.set_page_config(page_title="Ayada TDR", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body,[class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #F8FAFC; }
    h1, h2, h3 { color: #0F172A; font-weight: 700; letter-spacing: -0.025em; }
    [data-testid="stSidebar"] { background-color: #FFFFFF; border-right: 1px solid #E2E8F0; box-shadow: 2px 0 8px rgba(0,0,0,0.02); }
    .stTabs [data-baseweb="tab-list"] { background-color: #FFFFFF; padding: 4px; border-radius: 12px; border: 1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 10px 16px; border-radius: 8px !important; border: none !important; color: #64748B; font-weight: 500; background-color: transparent; transition: all 0.2s ease-in-out; }
    .stTabs [data-baseweb="tab"]:hover { color: #0F172A; background-color: #F1F5F9; }
    .stTabs [aria-selected="true"] { background-color: #3B82F6 !important; color: #FFFFFF !important; box-shadow: 0 2px 4px rgba(59,130,246,0.3); }
    .stButton>button { background-color: #0F172A; color: #FFFFFF; border: none; border-radius: 8px; padding: 10px 20px; font-weight: 600; transition: all 0.2s ease; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); width: 100%; }
    .stButton>button:hover { background-color: #334155; transform: translateY(-1px); box-shadow: 0 6px 8px -1px rgba(0,0,0,0.15); color: white !important; }
    .stTextInput>div>div>input, .stSelectbox>div>div>div { border-radius: 8px; border: 1px solid #CBD5E1; padding: 8px 12px; box-shadow: 0 1px 2px rgba(0,0,0,0.02); }
    [data-testid="stExpander"] { background-color: #FFFFFF; border-radius: 12px; border: 1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    [data-testid="stFileUploadDropzone"] { border: 2px dashed #CBD5E1; border-radius: 12px; background-color: #FFFFFF; }
    [data-testid="stFileUploadDropzone"]:hover { border-color: #3B82F6; background-color: #EFF6FF; }
    table { border-collapse: collapse; width: 100%; background-color: white; box-shadow: 0px 1px 3px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }
    th { background-color: #0F172A; color: white; }
    th, td { padding: 12px 16px; border-bottom: 1px solid #E2E8F0; }
    </style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# STOCK DASHBOARD FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def normalize_header(value):
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def find_column(df, aliases):
    columns_by_name = {}
    for column in df.columns:
        normalized = normalize_header(column)
        if normalized and normalized not in columns_by_name:
            columns_by_name[normalized] = column
    for alias in aliases:
        match = columns_by_name.get(normalize_header(alias))
        if match is not None:
            return match
    return None


def to_numeric_series(values):
    cleaned = values.astype(str).str.replace(r"[\s\u00a0\u202f]", "", regex=True)
    cleaned = cleaned.str.replace(",", ".", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")


def standardize_stock_columns(df):
    df = df.copy()
    df.columns = [str(column).strip() for column in df.columns]

    # Use 'Marque' for supplier views when a supplier name is unavailable.
    supplier_source = find_column(df, ["fournisseur", "supplier", "vendor"])
    brand_source = find_column(df, ["marque", "brand"])
    if supplier_source is not None:
        df["fournisseur"] = df[supplier_source]
    elif brand_source is not None:
        df["fournisseur"] = df[brand_source]
    else:
        df["fournisseur"] = ""

    text_aliases = {
        "barcode": ["barcode", "code-barres", "code barre", "ean", "ean13"],
        "couleur": ["couleur", "color", "colour"],
        "taille": ["taille", "size"],
        "designation": ["designation produit", "designation", "product name", "nom du produit", "libelle", "produit"],
        "rayon": ["rayon", "genre", "gender", "sexe"],
        "famille": ["famille", "family"],
        "categorie": ["categorie", "category"],
        "ssfamille": ["ssfamille", "sous-famille", "sous-categorie", "subcategory", "subfamily"],
    }
    for target, aliases in text_aliases.items():
        source = find_column(df, aliases)
        if source is not None:
            df[target] = df[source]

    if brand_source is not None:
        df["marque"] = df[brand_source]
    elif supplier_source is not None:
        df["marque"] = df[supplier_source]
    else:
        df["marque"] = ""

    quantity_source = find_column(df, [
        "Qté stock dispo", "Quantité disponible", "quantite disponible",
        "available quantity", "quantity available", "stock available"
    ])
    if quantity_source is not None:
        quantity = to_numeric_series(df[quantity_source])
    else:
        inventory_source = find_column(df, ["Quantité inventoriée", "quantity on hand", "inventory quantity"])
        reserved_source = find_column(df, ["Quantité réservée", "reserved quantity"])
        if inventory_source is None:
            raise ValueError(
                "Colonne de quantité introuvable. Utilisez « Quantité disponible » "
                "ou « Qté stock dispo » dans le fichier."
            )
        quantity = to_numeric_series(df[inventory_source])
        if reserved_source is not None:
            quantity = quantity - to_numeric_series(df[reserved_source]).fillna(0)
    df["Qté stock dispo"] = quantity.fillna(0)

    # Odoo's 'Valeur' is already a total valuation per inventory/location
    # row. Treating it as unit price would multiply the stock value twice.
    price_source = find_column(df, [
        "Prix Achat", "purchase price", "unit cost", "cout unitaire"
    ])
    value_source = find_column(df, ["Valeur"])
    is_odoo_export = (
        find_column(df, ["Emplacement", "Stock location"]) is not None
        and find_column(df, ["Quantité inventoriée"]) is not None
    )
    stock_value_aliases = [
        "Valeur Stock", "stock value", "inventory value",
        "valeur totale du stock"
    ]
    if is_odoo_export:
        stock_value_aliases.append("Valeur")
    stock_value_source = find_column(df, stock_value_aliases)

    if price_source is not None:
        df["Prix Achat"] = to_numeric_series(df[price_source]).fillna(0)
    elif is_odoo_export and value_source is not None:
        row_value = to_numeric_series(df[value_source]).fillna(0)
        inventory_source = find_column(df, ["Quantité inventoriée"])
        units = to_numeric_series(df[inventory_source])
        units = units.where(units.ne(0))
        df["Prix Achat"] = (
            (row_value / units)
            .replace([float("inf"), -float("inf")], 0)
            .fillna(0)
        )
    elif value_source is not None:
        # Preserve earlier non-Odoo exports, where 'Valeur' was a unit cost.
        df["Prix Achat"] = to_numeric_series(df[value_source]).fillna(0)
    else:
        df["Prix Achat"] = 0.0

    calculated_value = df["Qté stock dispo"] * df["Prix Achat"]
    if stock_value_source is not None:
        source_value = to_numeric_series(df[stock_value_source])
        df["Valeur Stock"] = source_value.where(
            source_value.notna(), calculated_value
        ).fillna(0)
    else:
        df["Valeur Stock"] = calculated_value.fillna(0)

    for column in [
        "fournisseur", "barcode", "couleur", "taille", "designation",
        "rayon", "marque", "famille", "categorie", "ssfamille"
    ]:
        if column not in df.columns:
            df[column] = ""
        df[column] = df[column].fillna("").astype(str).str.strip()

    # Prevent sparse numeric barcode columns from displaying a trailing '.0'.
    df["barcode"] = df["barcode"].str.replace(r"\.0$", "", regex=True)
    return df, supplier_source is None and brand_source is not None


def clean_numeric_columns(df):
    for column in ["Prix Achat", "Qté stock dispo", "Valeur Stock"]:
        if column in df.columns:
            df[column] = to_numeric_series(df[column]).fillna(0)
    return df


def clean_size_column(df):
    for column, prefix in [("taille", "taille"), ("couleur", "couleur")]:
        if column in df.columns:
            df[column] = df[column].fillna("").astype(str).str.strip()
            df[column] = df[column].str.replace(
                rf"^\s*{prefix}\s*:\s*", "", regex=True, case=False
            )
    return df


def highlight_row_if_one(row):
    if row['Qté stock dispo'] == 1:
        return ['background-color: #FEE2E2; color: #991B1B' for _ in row]
    return [''] * len(row)

def display_supplier_info(df, fournisseur):
    colonnes_afficher = ['fournisseur', 'barcode', 'couleur', 'taille', 'designation', 'rayon', 'marque', 'famille', 'Qté stock dispo', 'Valeur Stock']
    fournisseur = fournisseur.strip().upper()
    df['fournisseur'] = df['fournisseur'].fillna('')
    df_filtered = df[df['fournisseur'].str.upper() == fournisseur] if fournisseur else pd.DataFrame(columns=colonnes_afficher)
    if not df_filtered.empty:
        designations_rayons = df_filtered.groupby(['designation', 'rayon']).size().reset_index(name='Nombre de références')
        designations_rayons = designations_rayons.sort_values(['designation', 'rayon'])
        with st.expander(f"Désignations disponibles pour {fournisseur}", expanded=True):
            designations_rayons['selection'] = designations_rayons.apply(lambda x: f"{x['designation']} ({x['rayon']})", axis=1)
            selected = st.selectbox("Sélectionnez une désignation pour voir les tailles manquantes", designations_rayons['selection'])
            selected_design, selected_rayon = selected.rsplit(" (", 1)
            selected_rayon = selected_rayon[:-1]
            filtered = df_filtered[(df_filtered['designation'] == selected_design) & (df_filtered['rayon'] == selected_rayon)]
            # Do not use US size grids for EU shoes or nonnumeric sizes.
            raw_sizes = filtered['taille'].fillna('').astype(str)
            parsed = pd.to_numeric(
                raw_sizes.str.replace(r'(?i)US
            def extract_size_value(size_str):
                try:
                    cleaned = str(size_str).upper().replace('US', '').strip().replace(',', '.')
                    if '.' in cleaned:
                        int_part, dec_part = cleaned.split('.', 1)
                        cleaned = f"{int_part.lstrip('0') or '0'}.{dec_part}"
                    else:
                        cleaned = cleaned.lstrip('0') or '0'
                    return float(cleaned)
                except:
                    return None
            size_qtys = {}
            size_mapping = {}
            for _, row in filtered.iterrows():
                size = row['taille']
                qty = row['Qté stock dispo']
                size_value = extract_size_value(size)
                if size_value is not None:
                    if size_value not in size_qtys:
                        size_qtys[size_value] = 0
                        size_mapping[size_value] = str(size)
                    size_qtys[size_value] += qty
                else:
                    if size not in size_qtys:
                        size_qtys[size] = 0
                    size_qtys[size] += qty
            if selected_rayon.upper() in ['FEMME', 'HOMME']:
                missing_sizes = [str(e) for e in expected_sizes if float(e) not in [s for s in size_qtys.keys() if isinstance(s, float)]]
            else:
                missing_sizes = []
            st.markdown(f"**Tailles disponibles pour {selected_design} ({selected_rayon}):**")
            display_sizes = []
            for size in sorted(size_qtys.keys(), key=lambda value: (0, value) if isinstance(value, float) else (1, str(value))):
                qty = size_qtys[size]
                display_size = size_mapping.get(size, str(size))
                display_text = f"{display_size} ({qty})"
                if qty == 1:
                    display_text = f"<span style='color:#DC2626; font-weight:bold;'>{display_text}</span>"
                display_sizes.append(display_text)
            st.markdown(", ".join(display_sizes), unsafe_allow_html=True)
            if missing_sizes:
                st.markdown(f"**Tailles manquantes ({selected_rayon}):**")
                st.info(", ".join(missing_sizes))
            elif expected_sizes:
                st.success("Toutes les tailles attendues sont disponibles.")
            else:
                st.info(
                    "La grille de tailles attendues n'est pas disponible pour "
                    "ce modèle ; seules les tailles observées sont affichées."
                )
    return df_filtered[colonnes_afficher]

def display_designation_info(df, designation):
    colonnes_a_afficher = ['barcode', 'taille', 'rayon', 'couleur', 'designation', 'Qté stock dispo']
    designation = designation.strip().upper()
    df['designation'] = df['designation'].fillna('')
    df_filtered = df[df['designation'].str.upper() == designation] if designation else pd.DataFrame(columns=colonnes_a_afficher)
    def normalize_size(size):
        if pd.isna(size): return ''
        size_str = str(size).strip()
        if '.' in size_str:
            int_part, dec_part = size_str.split('.', 1)
            size_str = f"{int_part.lstrip('0') or '0'}.{dec_part}"
        else:
            size_str = size_str.lstrip('0') or '0'
        return size_str
    if 'taille' in df_filtered.columns:
        df_filtered['taille_normalisee'] = df_filtered['taille'].apply(normalize_size)
    sum_by_size = pd.DataFrame()
    if not df_filtered.empty and 'taille_normalisee' in df_filtered.columns:
        df_filtered['taille_num'] = pd.to_numeric(df_filtered['taille_normalisee'], errors='coerce')
        sum_by_size = df_filtered.groupby(['taille_normalisee', 'rayon'])['Qté stock dispo'].sum().reset_index()
        sum_by_size.columns = ['Taille', 'Rayon', 'Total Qté dispo']
        sum_by_size['taille_num'] = pd.to_numeric(sum_by_size['Taille'], errors='coerce')
        sum_by_size = sum_by_size.sort_values('taille_num').drop(columns=['taille_num'])
    def highlight_row_if_one_cond(row):
        if 'taille_normalisee' in row and row['taille_normalisee'] in sum_by_size['Taille'].values:
            mask = (sum_by_size['Taille'] == row['taille_normalisee'])
            if 'rayon' in sum_by_size.columns:
                mask &= (sum_by_size['Rayon'] == row['rayon'])
            total = sum_by_size.loc[mask, 'Total Qté dispo'].values[0] if any(mask) else 0
            if total == 1:
                return ['background-color: #FEE2E2; color: #991B1B'] * len(row)
        return [''] * len(row)
    if not df_filtered.empty and 'taille_num' in df_filtered.columns:
        df_filtered = df_filtered.sort_values('taille_num')
    st.dataframe(df_filtered[colonnes_a_afficher].style.apply(highlight_row_if_one_cond, axis=1), use_container_width=True)
    if not sum_by_size.empty:
        sum_homme = sum_by_size[sum_by_size['Rayon'] == 'HOMME']
        sum_femme = sum_by_size[sum_by_size['Rayon'] == 'FEMME']
        def highlight_total_if_one(val):
            return 'background-color: #FEE2E2; color: #991B1B' if val == 1 else ''
        col1, col2 = st.columns(2)
        if not sum_homme.empty:
            with col1:
                st.subheader("Somme par taille - HOMME")
                st.dataframe(sum_homme[['Taille', 'Total Qté dispo']].style.map(highlight_total_if_one, subset=['Total Qté dispo']), use_container_width=True)
        if not sum_femme.empty:
            with col2:
                st.subheader("Somme par taille - FEMME")
                st.dataframe(sum_femme[['Taille', 'Total Qté dispo']].style.map(highlight_total_if_one, subset=['Total Qté dispo']), use_container_width=True)

def filter_negative_stock(df):
    colonnes_affichier = ['fournisseur', 'barcode', 'couleur', 'taille', 'designation', 'rayon', 'marque', 'famille', 'Qté stock dispo', 'Valeur Stock']
    df['Qté stock dispo'] = df['Qté stock dispo'].fillna(0)
    return df[df['Qté stock dispo'] < 0][colonnes_affichier]

def display_anita_sizes(df):
    df_anita = df[df['fournisseur'].str.upper() == "ANITA"]
    tailles = [f"{num}{letter}" for num in [85, 90, 95, 100, 105, 110] for letter in 'ABCDEF']
    df_anita_sizes = df_anita[df_anita['taille'].isin(tailles)]
    df_anita_sizes = df_anita_sizes.groupby('taille')['Qté stock dispo'].sum().reindex(tailles, fill_value=0)
    return df_anita_sizes.replace(0, "Nul")

def display_sidas_levels(df):
    df['fournisseur'] = df['fournisseur'].fillna('')
    df = df.dropna(subset=['couleur', 'taille'])
    df_sidas = df[df['fournisseur'].str.upper().str.contains("SIDAS")]
    levels = ['LOW', 'MID', 'HIGH']
    sizes = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
    results = {}
    for level in levels:
        df_sidas_level = df_sidas[df_sidas['couleur'].str.upper() == level]
        df_sizes = df_sidas_level[df_sidas_level['taille'].isin(sizes)]
        df_sizes_grouped = df_sizes.groupby(['taille', 'designation'])['Qté stock dispo'].sum().unstack(fill_value=0).replace(0, "Nul")
        df_sizes_with_designation = df_sizes_grouped.stack().reset_index().rename(columns={0: 'Qté stock dispo'})
        results[level] = df_sizes_with_designation
        unavailable = [s for s in sizes if s not in df_sidas_level['taille'].unique()]
        if unavailable:
            st.warning(f"Tailles indisponibles pour SIDAS niveau {level}: {', '.join(unavailable)}")
        else:
            st.success(f"Toutes les tailles SIDAS niveau {level} sont en stock.")
    return results

def total_stock_value_by_supplier(df):
    result = pd.DataFrame({
        "Marque / fournisseur": df["fournisseur"].fillna("").astype(str).str.strip().replace("", "Non renseigné"),
        "Valeur Totale HT": pd.to_numeric(df["Valeur Stock"], errors="coerce").fillna(0)
    })
    result = result.groupby("Marque / fournisseur", as_index=False)["Valeur Totale HT"].sum()
    return result.sort_values(by="Valeur Totale HT", ascending=False)


def sort_sizes(df):
    df['taille'] = pd.Categorical(df['taille'],
        categories=sorted(df['taille'].unique(),
            key=lambda x: (int(x[:-1]), x[-1]) if str(x)[:-1].isdigit() else (float('inf'), x)),
        ordered=True)
    return df.sort_values('taille')

def display_stock_by_family(df):
    st.subheader("Stock par famille et catégorie")
    work = df.copy()
    family_values = sorted(value for value in work["famille"].dropna().astype(str).str.strip().unique() if value)
    family_options = ["Toutes"] + family_values
    selected_family = st.selectbox("Filtrer par famille", family_options)

    if selected_family != "Toutes":
        work = work[work["famille"].astype(str).str.strip() == selected_family]

    category_values = sorted(value for value in work["categorie"].dropna().astype(str).str.strip().unique() if value)
    if category_values:
        selected_category = st.selectbox("Filtrer par catégorie", ["Toutes"] + category_values)
        if selected_category != "Toutes":
            work = work[work["categorie"].astype(str).str.strip() == selected_category]

    total_stock = work["Qté stock dispo"].sum()
    total_value = work["Valeur Stock"].sum()
    col1, col2 = st.columns(2)
    col1.metric("Quantité disponible", f"{total_stock:,.0f}".replace(",", " "))
    col2.metric("Valeur totale du stock", f"{total_value:,.2f} €".replace(",", " "))

    columns = [
        "famille", "categorie", "ssfamille", "rayon", "fournisseur",
        "couleur", "taille", "designation", "Qté stock dispo", "Valeur Stock"
    ]
    display = work[columns].rename(columns={
        "famille": "Famille",
        "categorie": "Catégorie",
        "ssfamille": "Sous-catégorie",
        "rayon": "Genre",
        "fournisseur": "Marque / fournisseur",
        "couleur": "Couleur",
        "taille": "Taille",
        "designation": "Désignation",
    })
    st.dataframe(display.style.apply(highlight_row_if_one, axis=1), use_container_width=True)


def display_specific_designations(df):
    """Show shoe sizes using the actual EU/US sizes in the uploaded stock."""
    work = df.copy()
    for col in ["marque", "fournisseur", "designation", "taille",
                "famille", "ssfamille", "rayon"]:
        if col not in work.columns:
            work[col] = ""
        work[col] = work[col].fillna("").astype(str).str.strip()

    work["Qté stock dispo"] = pd.to_numeric(
        work["Qté stock dispo"], errors="coerce"
    ).fillna(0)
    work["brand_name"] = work["marque"].where(
        work["marque"].ne(""), work["fournisseur"]
    ).str.upper().str.strip()

    if work["famille"].ne("").any() or work["ssfamille"].ne("").any():
        mask = (
            work["famille"].str.contains("CHAUSS", case=False, na=False)
            | work["ssfamille"].str.contains("CHAUSS", case=False, na=False)
        )
    else:
        mask = work["designation"].str.contains(
            r"RUNNING|TRAIL|RANDO|CHAUSS|SHOE", case=False, na=False
        )
    work = work.loc[
        mask & work["brand_name"].ne("") & work["designation"].ne("")
    ].copy()
    if work.empty:
        st.info("Aucune chaussure identifiable dans cet export.")
        return

    supplier = st.selectbox(
        "Choisissez une marque de chaussures",
        sorted(work["brand_name"].unique().tolist())
    )
    work = work.loc[work["brand_name"] == supplier]

    def number_from_size(raw):
        label = str(raw).upper().strip().replace(",", ".")
        label = re.sub(r"(?:US|UK|EU)$", "", label).strip()
        for symbol, fraction in [
            ("½", " 1/2"), ("⅓", " 1/3"), ("⅔", " 2/3"),
            ("¼", " 1/4"), ("¾", " 3/4")
        ]:
            label = label.replace(symbol, fraction)
        match = re.fullmatch(
            r"(\d+(?:\.\d+)?)(?:\s+(\d+)\s*/\s*(\d+))?", label
        )
        if not match:
            return None
        value = float(match.group(1))
        if match.group(2):
            den = int(match.group(3))
            if den == 0:
                return None
            value += int(match.group(2)) / den
        return value

    def size_label(value, step, suffix):
        integer = int(value)
        fraction = value - integer
        if abs(step - 1 / 3) < 0.001:
            n = round(fraction * 3)
            if n == 3:
                integer += 1
                n = 0
            label = f"{integer} {n}/3" if n else str(integer)
        else:
            label = f"{value:.1f}".rstrip("0").rstrip(".")
        return label + suffix

    results = []
    for (name, rayon), group in work.groupby(
        ["designation", "rayon"], dropna=False, sort=True
    ):
        quantities = group.groupby("taille")["Qté stock dispo"].sum()
        available = sorted(
            size for size, qty in quantities.items() if size and qty > 0
        )
        unavailable = sorted(
            size for size, qty in quantities.items() if size and qty <= 0
        )
        values = sorted({
            round(n, 4) for n in
            (number_from_size(size) for size in quantities.index)
            if n is not None
        })
        missing = []
        if len(values) > 1:
            raw_sizes = [str(size).upper() for size in quantities.index]
            third_sizes = any(
                re.search(r"[12]\s*/\s*3|[⅓⅔]", size)
                for size in raw_sizes
            )
            half_sizes = any(
                abs(v * 2 - round(v * 2)) < 0.001
                and abs(v - round(v)) > 0.001 for v in values
            )
            step = (1 / 3 if third_sizes else
                    0.5 if half_sizes or values[-1] < 20 else 1.0)
            suffix = "US" if any("US" in size for size in raw_sizes) else ""
            count = round((values[-1] - values[0]) / step)
            if 1 < count <= 120:
                for k in range(1, count):
                    candidate = values[0] + k * step
                    if not any(abs(candidate - v) < 0.02 for v in values):
                        missing.append(size_label(candidate, step, suffix))

        results.append({
            "Modèle": name,
            "Genre": rayon,
            "Tailles en stock": ", ".join(available) or "Aucune",
            "Tailles sans stock": ", ".join(unavailable) or "—",
            "Lacunes entre tailles observées": ", ".join(missing) or "—"
        })

    result = pd.DataFrame(results)
    st.subheader(f"{supplier} — disponibilité des tailles")
    st.caption(
        "Les tailles sans stock ont une quantité nulle ou négative dans "
        "l'export. Les lacunes sont inférées uniquement entre les tailles "
        "observées ; l'export ne contient pas le catalogue complet."
    )
    st.dataframe(result, use_container_width=True)
    export_name = re.sub(r"[^a-z0-9_-]+", "_", supplier.lower()) or "marque"
    col1, col2 = st.columns(2)
    with col1:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            result.to_excel(writer, sheet_name="Tailles", index=False)
        st.download_button(
            "📊 Exporter en Excel (XLSX)", data=output.getvalue(),
            file_name=f"{export_name}_tailles.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col2:
        st.download_button(
            "📄 Exporter en CSV",
            data=result.to_csv(index=False, sep=";"),
            file_name=f"{export_name}_tailles.csv", mime="text/csv"
        )


# ═══════════════════════════════════════════════════════════════
# MAIN APP
# ═══════════════════════════════════════════════════════════════

st.title("Ayada TDR - Tableau de Bord Stock")
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3081/3081840.png", width=50)
st.sidebar.markdown("### Menu Principal")
st.sidebar.info("Téléchargez un fichier CSV ou Excel pour commencer l'analyse.")
fichier_telecharge = st.sidebar.file_uploader("📂 Fichier source stock", type=["csv", "xlsx"])

if fichier_telecharge is not None:
    extension_fichier = fichier_telecharge.name.rsplit(".", 1)[-1].lower()
    try:
        with st.spinner("Chargement et préparation des données..."):
            if extension_fichier == "csv":
                df = None
                csv_bytes = fichier_telecharge.getvalue()
                for encoding in ("utf-8-sig", "cp1252", "ISO-8859-1"):
                    try:
                        df = pd.read_csv(
                            BytesIO(csv_bytes), encoding=encoding, sep=None, engine="python"
                        )
                        break
                    except UnicodeDecodeError:
                        continue
                if df is None:
                    raise ValueError("Impossible de lire l'encodage du fichier CSV.")
            elif extension_fichier in ("xlsx", "xls"):
                df = pd.read_excel(fichier_telecharge, sheet_name=0)
            else:
                raise ValueError("Format non pris en charge. Importez un fichier CSV ou Excel.")

            if df.empty:
                raise ValueError("Le fichier ne contient aucune ligne de stock.")

            # Virtual inventory adjustments are accounting counterparts, not
            # warehouse stock. Exclude them from physical stock by default.
            excluded_adjustments = 0
            location_source = find_column(
                df, ["Emplacement", "Stock location", "Location"]
            )
            if location_source is not None:
                locations = df[location_source].fillna("").astype(str).str.casefold()
                virtual_locations = locations.str.contains(
                    r"inventory adjustments?|ajustements? d['’ ]inventaire",
                    na=False, regex=True
                )
                if virtual_locations.any():
                    include_adjustments = st.sidebar.checkbox(
                        "Inclure les emplacements virtuels (ajustements d'inventaire)",
                        value=False
                    )
                    if not include_adjustments:
                        excluded_adjustments = int(virtual_locations.sum())
                        df = df.loc[~virtual_locations].copy()
                        if df.empty:
                            raise ValueError(
                                "Aucun stock physique après exclusion "
                                "des emplacements virtuels."
                            )

            uses_brand_as_supplier = (
                find_column(df, ["fournisseur", "supplier", "vendor"]) is None
                and find_column(df, ["marque", "brand"]) is not None
            )
            df, _ = standardize_stock_columns(df)
            df = clean_numeric_columns(df)
            df = clean_size_column(df)

            st.success(f"Données chargées avec succès — {len(df):,} lignes.".replace(",", " "))
            if excluded_adjustments:
                st.info(
                    f"{excluded_adjustments:,} lignes d'ajustement virtuel exclues "
                    "de l'analyse du stock physique. Vous pouvez les inclure "
                    "depuis le menu latéral."
                )
            if location_source is not None and find_column(df, ["Valeur"]) is not None:
                st.caption(
                    "Dans l'export Odoo, « Valeur » correspond à la "
                    "valorisation totale d'une ligne, pas au prix unitaire."
                )
            if uses_brand_as_supplier:
                st.info(
                    "Cet export ne contient pas de fournisseur dédié. "
                    "Les vues par fournisseur utilisent la colonne « Marque »."
                )

            tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
                "🏷️ Marque / fournisseur", "🔍 Modèle", "⚠️ Stock Négatif",
                "👙 Anita", "🦶 Sidas", "💰 Valeur Stock",
                "👟 Catégories", "📊 Tailles Manquantes"
            ])

            with tab1:
                fournisseur = st.text_input("Rechercher une marque ou un fournisseur :")
                df_filtered = display_supplier_info(df.copy(), fournisseur)
                if not df_filtered.empty:
                    display = df_filtered.rename(columns={"fournisseur": "Marque / fournisseur"})
                    st.dataframe(display.style.apply(highlight_row_if_one, axis=1), use_container_width=True)
                elif fournisseur:
                    st.warning("Aucune information disponible pour cette marque ou ce fournisseur.")

            with tab2:
                designation = st.text_input("Rechercher un modèle exact :")
                display_designation_info(df.copy(), designation)

            with tab3:
                st.subheader("Produits en stock négatif")
                negative_stock = filter_negative_stock(df.copy()).rename(
                    columns={"fournisseur": "Marque / fournisseur"}
                )
                st.dataframe(negative_stock.style.apply(highlight_row_if_one, axis=1), use_container_width=True)

            with tab4:
                st.subheader("Disponibilité Anita")
                st.dataframe(display_anita_sizes(df), use_container_width=True)

            with tab5:
                st.subheader("Disponibilité Semelles Sidas")
                for level, df_level in display_sidas_levels(df).items():
                    st.markdown(f"**Niveau {level}**")
                    st.dataframe(df_level.style.apply(highlight_row_if_one, axis=1), use_container_width=True)

            with tab6:
                st.subheader("Valorisation par marque / fournisseur")
                df_tv = total_stock_value_by_supplier(df)
                st.metric("Valeur Totale Globale du Stock", f"{df_tv['Valeur Totale HT'].sum():,.2f} €".replace(",", " "))
                st.dataframe(df_tv, use_container_width=True)

            with tab7:
                display_stock_by_family(df)

            with tab8:
                st.subheader("Analyse de la profondeur de gamme (Chaussures)")
                display_specific_designations(df.copy())

    except Exception as e:
        st.error(f"Impossible de traiter ce fichier stock : {str(e)}")


else:
    st.info("Utilisez la barre latérale pour charger un fichier stock pour commencer.")
, '', regex=True)
                         .str.replace(',', '.', regex=False),
                errors='coerce'
            ).dropna()
            is_eu = (
                raw_sizes.str.contains(r'\d{2}\s+[12]/3|[⅓⅔]', regex=True).any()
                or (not parsed.empty and parsed.median() >= 30)
            )
            if is_eu or parsed.empty:
                expected_sizes = []
            elif selected_rayon.upper() == 'FEMME':
                expected_sizes = [round(x * 0.5, 1) for x in range(10, 21)]
            elif selected_rayon.upper() == 'HOMME':
                expected_sizes = [round(x * 0.5, 1) for x in range(14, 29)]
            else:
                expected_sizes = []
            def extract_size_value(size_str):
                try:
                    cleaned = str(size_str).upper().replace('US', '').strip().replace(',', '.')
                    if '.' in cleaned:
                        int_part, dec_part = cleaned.split('.', 1)
                        cleaned = f"{int_part.lstrip('0') or '0'}.{dec_part}"
                    else:
                        cleaned = cleaned.lstrip('0') or '0'
                    return float(cleaned)
                except:
                    return None
            size_qtys = {}
            size_mapping = {}
            for _, row in filtered.iterrows():
                size = row['taille']
                qty = row['Qté stock dispo']
                size_value = extract_size_value(size)
                if size_value is not None:
                    if size_value not in size_qtys:
                        size_qtys[size_value] = 0
                        size_mapping[size_value] = str(size)
                    size_qtys[size_value] += qty
                else:
                    if size not in size_qtys:
                        size_qtys[size] = 0
                    size_qtys[size] += qty
            if selected_rayon.upper() in ['FEMME', 'HOMME']:
                missing_sizes = [str(e) for e in expected_sizes if float(e) not in [s for s in size_qtys.keys() if isinstance(s, float)]]
            else:
                missing_sizes = []
            st.markdown(f"**Tailles disponibles pour {selected_design} ({selected_rayon}):**")
            display_sizes = []
            for size in sorted(size_qtys.keys(), key=lambda value: (0, value) if isinstance(value, float) else (1, str(value))):
                qty = size_qtys[size]
                display_size = size_mapping.get(size, str(size))
                display_text = f"{display_size} ({qty})"
                if qty == 1:
                    display_text = f"<span style='color:#DC2626; font-weight:bold;'>{display_text}</span>"
                display_sizes.append(display_text)
            st.markdown(", ".join(display_sizes), unsafe_allow_html=True)
            if missing_sizes:
                st.markdown(f"**Tailles manquantes ({selected_rayon}):**")
                st.info(", ".join(missing_sizes))
            else:
                st.success("Toutes les tailles attendues sont disponibles.")
    return df_filtered[colonnes_afficher]

def display_designation_info(df, designation):
    colonnes_a_afficher = ['barcode', 'taille', 'rayon', 'couleur', 'designation', 'Qté stock dispo']
    designation = designation.strip().upper()
    df['designation'] = df['designation'].fillna('')
    df_filtered = df[df['designation'].str.upper() == designation] if designation else pd.DataFrame(columns=colonnes_a_afficher)
    def normalize_size(size):
        if pd.isna(size): return ''
        size_str = str(size).strip()
        if '.' in size_str:
            int_part, dec_part = size_str.split('.', 1)
            size_str = f"{int_part.lstrip('0') or '0'}.{dec_part}"
        else:
            size_str = size_str.lstrip('0') or '0'
        return size_str
    if 'taille' in df_filtered.columns:
        df_filtered['taille_normalisee'] = df_filtered['taille'].apply(normalize_size)
    sum_by_size = pd.DataFrame()
    if not df_filtered.empty and 'taille_normalisee' in df_filtered.columns:
        df_filtered['taille_num'] = pd.to_numeric(df_filtered['taille_normalisee'], errors='coerce')
        sum_by_size = df_filtered.groupby(['taille_normalisee', 'rayon'])['Qté stock dispo'].sum().reset_index()
        sum_by_size.columns = ['Taille', 'Rayon', 'Total Qté dispo']
        sum_by_size['taille_num'] = pd.to_numeric(sum_by_size['Taille'], errors='coerce')
        sum_by_size = sum_by_size.sort_values('taille_num').drop(columns=['taille_num'])
    def highlight_row_if_one_cond(row):
        if 'taille_normalisee' in row and row['taille_normalisee'] in sum_by_size['Taille'].values:
            mask = (sum_by_size['Taille'] == row['taille_normalisee'])
            if 'rayon' in sum_by_size.columns:
                mask &= (sum_by_size['Rayon'] == row['rayon'])
            total = sum_by_size.loc[mask, 'Total Qté dispo'].values[0] if any(mask) else 0
            if total == 1:
                return ['background-color: #FEE2E2; color: #991B1B'] * len(row)
        return [''] * len(row)
    if not df_filtered.empty and 'taille_num' in df_filtered.columns:
        df_filtered = df_filtered.sort_values('taille_num')
    st.dataframe(df_filtered[colonnes_a_afficher].style.apply(highlight_row_if_one_cond, axis=1), use_container_width=True)
    if not sum_by_size.empty:
        sum_homme = sum_by_size[sum_by_size['Rayon'] == 'HOMME']
        sum_femme = sum_by_size[sum_by_size['Rayon'] == 'FEMME']
        def highlight_total_if_one(val):
            return 'background-color: #FEE2E2; color: #991B1B' if val == 1 else ''
        col1, col2 = st.columns(2)
        if not sum_homme.empty:
            with col1:
                st.subheader("Somme par taille - HOMME")
                st.dataframe(sum_homme[['Taille', 'Total Qté dispo']].style.map(highlight_total_if_one, subset=['Total Qté dispo']), use_container_width=True)
        if not sum_femme.empty:
            with col2:
                st.subheader("Somme par taille - FEMME")
                st.dataframe(sum_femme[['Taille', 'Total Qté dispo']].style.map(highlight_total_if_one, subset=['Total Qté dispo']), use_container_width=True)

def filter_negative_stock(df):
    colonnes_affichier = ['fournisseur', 'barcode', 'couleur', 'taille', 'designation', 'rayon', 'marque', 'famille', 'Qté stock dispo', 'Valeur Stock']
    df['Qté stock dispo'] = df['Qté stock dispo'].fillna(0)
    return df[df['Qté stock dispo'] < 0][colonnes_affichier]

def display_anita_sizes(df):
    df_anita = df[df['fournisseur'].str.upper() == "ANITA"]
    tailles = [f"{num}{letter}" for num in [85, 90, 95, 100, 105, 110] for letter in 'ABCDEF']
    df_anita_sizes = df_anita[df_anita['taille'].isin(tailles)]
    df_anita_sizes = df_anita_sizes.groupby('taille')['Qté stock dispo'].sum().reindex(tailles, fill_value=0)
    return df_anita_sizes.replace(0, "Nul")

def display_sidas_levels(df):
    df['fournisseur'] = df['fournisseur'].fillna('')
    df = df.dropna(subset=['couleur', 'taille'])
    df_sidas = df[df['fournisseur'].str.upper().str.contains("SIDAS")]
    levels = ['LOW', 'MID', 'HIGH']
    sizes = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
    results = {}
    for level in levels:
        df_sidas_level = df_sidas[df_sidas['couleur'].str.upper() == level]
        df_sizes = df_sidas_level[df_sidas_level['taille'].isin(sizes)]
        df_sizes_grouped = df_sizes.groupby(['taille', 'designation'])['Qté stock dispo'].sum().unstack(fill_value=0).replace(0, "Nul")
        df_sizes_with_designation = df_sizes_grouped.stack().reset_index().rename(columns={0: 'Qté stock dispo'})
        results[level] = df_sizes_with_designation
        unavailable = [s for s in sizes if s not in df_sidas_level['taille'].unique()]
        if unavailable:
            st.warning(f"Tailles indisponibles pour SIDAS niveau {level}: {', '.join(unavailable)}")
        else:
            st.success(f"Toutes les tailles SIDAS niveau {level} sont en stock.")
    return results

def total_stock_value_by_supplier(df):
    result = pd.DataFrame({
        "Marque / fournisseur": df["fournisseur"].fillna("").astype(str).str.strip().replace("", "Non renseigné"),
        "Valeur Totale HT": pd.to_numeric(df["Valeur Stock"], errors="coerce").fillna(0)
    })
    result = result.groupby("Marque / fournisseur", as_index=False)["Valeur Totale HT"].sum()
    return result.sort_values(by="Valeur Totale HT", ascending=False)


def sort_sizes(df):
    df['taille'] = pd.Categorical(df['taille'],
        categories=sorted(df['taille'].unique(),
            key=lambda x: (int(x[:-1]), x[-1]) if str(x)[:-1].isdigit() else (float('inf'), x)),
        ordered=True)
    return df.sort_values('taille')

def display_stock_by_family(df):
    st.subheader("Stock par famille et catégorie")
    work = df.copy()
    family_values = sorted(value for value in work["famille"].dropna().astype(str).str.strip().unique() if value)
    family_options = ["Toutes"] + family_values
    selected_family = st.selectbox("Filtrer par famille", family_options)

    if selected_family != "Toutes":
        work = work[work["famille"].astype(str).str.strip() == selected_family]

    category_values = sorted(value for value in work["categorie"].dropna().astype(str).str.strip().unique() if value)
    if category_values:
        selected_category = st.selectbox("Filtrer par catégorie", ["Toutes"] + category_values)
        if selected_category != "Toutes":
            work = work[work["categorie"].astype(str).str.strip() == selected_category]

    total_stock = work["Qté stock dispo"].sum()
    total_value = work["Valeur Stock"].sum()
    col1, col2 = st.columns(2)
    col1.metric("Quantité disponible", f"{total_stock:,.0f}".replace(",", " "))
    col2.metric("Valeur totale du stock", f"{total_value:,.2f} €".replace(",", " "))

    columns = [
        "famille", "categorie", "ssfamille", "rayon", "fournisseur",
        "couleur", "taille", "designation", "Qté stock dispo", "Valeur Stock"
    ]
    display = work[columns].rename(columns={
        "famille": "Famille",
        "categorie": "Catégorie",
        "ssfamille": "Sous-catégorie",
        "rayon": "Genre",
        "fournisseur": "Marque / fournisseur",
        "couleur": "Couleur",
        "taille": "Taille",
        "designation": "Désignation",
    })
    st.dataframe(display.style.apply(highlight_row_if_one, axis=1), use_container_width=True)


def display_specific_designations(df):
    """Show shoe sizes using the actual EU/US sizes in the uploaded stock."""
    work = df.copy()
    for col in ["marque", "fournisseur", "designation", "taille",
                "famille", "ssfamille", "rayon"]:
        if col not in work.columns:
            work[col] = ""
        work[col] = work[col].fillna("").astype(str).str.strip()

    work["Qté stock dispo"] = pd.to_numeric(
        work["Qté stock dispo"], errors="coerce"
    ).fillna(0)
    work["brand_name"] = work["marque"].where(
        work["marque"].ne(""), work["fournisseur"]
    ).str.upper().str.strip()

    if work["famille"].ne("").any() or work["ssfamille"].ne("").any():
        mask = (
            work["famille"].str.contains("CHAUSS", case=False, na=False)
            | work["ssfamille"].str.contains("CHAUSS", case=False, na=False)
        )
    else:
        mask = work["designation"].str.contains(
            r"RUNNING|TRAIL|RANDO|CHAUSS|SHOE", case=False, na=False
        )
    work = work.loc[
        mask & work["brand_name"].ne("") & work["designation"].ne("")
    ].copy()
    if work.empty:
        st.info("Aucune chaussure identifiable dans cet export.")
        return

    supplier = st.selectbox(
        "Choisissez une marque de chaussures",
        sorted(work["brand_name"].unique().tolist())
    )
    work = work.loc[work["brand_name"] == supplier]

    def number_from_size(raw):
        label = str(raw).upper().strip().replace(",", ".")
        label = re.sub(r"(?:US|UK|EU)$", "", label).strip()
        for symbol, fraction in [
            ("½", " 1/2"), ("⅓", " 1/3"), ("⅔", " 2/3"),
            ("¼", " 1/4"), ("¾", " 3/4")
        ]:
            label = label.replace(symbol, fraction)
        match = re.fullmatch(
            r"(\d+(?:\.\d+)?)(?:\s+(\d+)\s*/\s*(\d+))?", label
        )
        if not match:
            return None
        value = float(match.group(1))
        if match.group(2):
            den = int(match.group(3))
            if den == 0:
                return None
            value += int(match.group(2)) / den
        return value

    def size_label(value, step, suffix):
        integer = int(value)
        fraction = value - integer
        if abs(step - 1 / 3) < 0.001:
            n = round(fraction * 3)
            if n == 3:
                integer += 1
                n = 0
            label = f"{integer} {n}/3" if n else str(integer)
        else:
            label = f"{value:.1f}".rstrip("0").rstrip(".")
        return label + suffix

    results = []
    for (name, rayon), group in work.groupby(
        ["designation", "rayon"], dropna=False, sort=True
    ):
        quantities = group.groupby("taille")["Qté stock dispo"].sum()
        available = sorted(
            size for size, qty in quantities.items() if size and qty > 0
        )
        unavailable = sorted(
            size for size, qty in quantities.items() if size and qty <= 0
        )
        values = sorted({
            round(n, 4) for n in
            (number_from_size(size) for size in quantities.index)
            if n is not None
        })
        missing = []
        if len(values) > 1:
            raw_sizes = [str(size).upper() for size in quantities.index]
            third_sizes = any(
                re.search(r"[12]\s*/\s*3|[⅓⅔]", size)
                for size in raw_sizes
            )
            half_sizes = any(
                abs(v * 2 - round(v * 2)) < 0.001
                and abs(v - round(v)) > 0.001 for v in values
            )
            step = (1 / 3 if third_sizes else
                    0.5 if half_sizes or values[-1] < 20 else 1.0)
            suffix = "US" if any("US" in size for size in raw_sizes) else ""
            count = round((values[-1] - values[0]) / step)
            if 1 < count <= 120:
                for k in range(1, count):
                    candidate = values[0] + k * step
                    if not any(abs(candidate - v) < 0.02 for v in values):
                        missing.append(size_label(candidate, step, suffix))

        results.append({
            "Modèle": name,
            "Genre": rayon,
            "Tailles en stock": ", ".join(available) or "Aucune",
            "Tailles sans stock": ", ".join(unavailable) or "—",
            "Lacunes entre tailles observées": ", ".join(missing) or "—"
        })

    result = pd.DataFrame(results)
    st.subheader(f"{supplier} — disponibilité des tailles")
    st.caption(
        "Les tailles sans stock ont une quantité nulle ou négative dans "
        "l'export. Les lacunes sont inférées uniquement entre les tailles "
        "observées ; l'export ne contient pas le catalogue complet."
    )
    st.dataframe(result, use_container_width=True)
    export_name = re.sub(r"[^a-z0-9_-]+", "_", supplier.lower()) or "marque"
    col1, col2 = st.columns(2)
    with col1:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            result.to_excel(writer, sheet_name="Tailles", index=False)
        st.download_button(
            "📊 Exporter en Excel (XLSX)", data=output.getvalue(),
            file_name=f"{export_name}_tailles.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col2:
        st.download_button(
            "📄 Exporter en CSV",
            data=result.to_csv(index=False, sep=";"),
            file_name=f"{export_name}_tailles.csv", mime="text/csv"
        )


# ═══════════════════════════════════════════════════════════════
# MAIN APP
# ═══════════════════════════════════════════════════════════════

st.title("Ayada TDR - Tableau de Bord Stock")
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3081/3081840.png", width=50)
st.sidebar.markdown("### Menu Principal")
st.sidebar.info("Téléchargez un fichier CSV ou Excel pour commencer l'analyse.")
fichier_telecharge = st.sidebar.file_uploader("📂 Fichier source stock", type=["csv", "xlsx"])

if fichier_telecharge is not None:
    extension_fichier = fichier_telecharge.name.rsplit(".", 1)[-1].lower()
    try:
        with st.spinner("Chargement et préparation des données..."):
            if extension_fichier == "csv":
                df = None
                csv_bytes = fichier_telecharge.getvalue()
                for encoding in ("utf-8-sig", "cp1252", "ISO-8859-1"):
                    try:
                        df = pd.read_csv(
                            BytesIO(csv_bytes), encoding=encoding, sep=None, engine="python"
                        )
                        break
                    except UnicodeDecodeError:
                        continue
                if df is None:
                    raise ValueError("Impossible de lire l'encodage du fichier CSV.")
            elif extension_fichier in ("xlsx", "xls"):
                df = pd.read_excel(fichier_telecharge, sheet_name=0)
            else:
                raise ValueError("Format non pris en charge. Importez un fichier CSV ou Excel.")

            if df.empty:
                raise ValueError("Le fichier ne contient aucune ligne de stock.")

            # Virtual inventory adjustments are accounting counterparts, not
            # warehouse stock. Exclude them from physical stock by default.
            excluded_adjustments = 0
            location_source = find_column(
                df, ["Emplacement", "Stock location", "Location"]
            )
            if location_source is not None:
                locations = df[location_source].fillna("").astype(str).str.casefold()
                virtual_locations = locations.str.contains(
                    r"inventory adjustments?|ajustements? d['’ ]inventaire",
                    na=False, regex=True
                )
                if virtual_locations.any():
                    include_adjustments = st.sidebar.checkbox(
                        "Inclure les emplacements virtuels (ajustements d'inventaire)",
                        value=False
                    )
                    if not include_adjustments:
                        excluded_adjustments = int(virtual_locations.sum())
                        df = df.loc[~virtual_locations].copy()
                        if df.empty:
                            raise ValueError(
                                "Aucun stock physique après exclusion "
                                "des emplacements virtuels."
                            )

            uses_brand_as_supplier = (
                find_column(df, ["fournisseur", "supplier", "vendor"]) is None
                and find_column(df, ["marque", "brand"]) is not None
            )
            df, _ = standardize_stock_columns(df)
            df = clean_numeric_columns(df)
            df = clean_size_column(df)

            st.success(f"Données chargées avec succès — {len(df):,} lignes.".replace(",", " "))
            if excluded_adjustments:
                st.info(
                    f"{excluded_adjustments:,} lignes d'ajustement virtuel exclues "
                    "de l'analyse du stock physique. Vous pouvez les inclure "
                    "depuis le menu latéral."
                )
            if location_source is not None and find_column(df, ["Valeur"]) is not None:
                st.caption(
                    "Dans l'export Odoo, « Valeur » correspond à la "
                    "valorisation totale d'une ligne, pas au prix unitaire."
                )
            if uses_brand_as_supplier:
                st.info(
                    "Cet export ne contient pas de fournisseur dédié. "
                    "Les vues par fournisseur utilisent la colonne « Marque »."
                )

            tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
                "🏷️ Marque / fournisseur", "🔍 Modèle", "⚠️ Stock Négatif",
                "👙 Anita", "🦶 Sidas", "💰 Valeur Stock",
                "👟 Catégories", "📊 Tailles Manquantes"
            ])

            with tab1:
                fournisseur = st.text_input("Rechercher une marque ou un fournisseur :")
                df_filtered = display_supplier_info(df.copy(), fournisseur)
                if not df_filtered.empty:
                    display = df_filtered.rename(columns={"fournisseur": "Marque / fournisseur"})
                    st.dataframe(display.style.apply(highlight_row_if_one, axis=1), use_container_width=True)
                elif fournisseur:
                    st.warning("Aucune information disponible pour cette marque ou ce fournisseur.")

            with tab2:
                designation = st.text_input("Rechercher un modèle exact :")
                display_designation_info(df.copy(), designation)

            with tab3:
                st.subheader("Produits en stock négatif")
                negative_stock = filter_negative_stock(df.copy()).rename(
                    columns={"fournisseur": "Marque / fournisseur"}
                )
                st.dataframe(negative_stock.style.apply(highlight_row_if_one, axis=1), use_container_width=True)

            with tab4:
                st.subheader("Disponibilité Anita")
                st.dataframe(display_anita_sizes(df), use_container_width=True)

            with tab5:
                st.subheader("Disponibilité Semelles Sidas")
                for level, df_level in display_sidas_levels(df).items():
                    st.markdown(f"**Niveau {level}**")
                    st.dataframe(df_level.style.apply(highlight_row_if_one, axis=1), use_container_width=True)

            with tab6:
                st.subheader("Valorisation par marque / fournisseur")
                df_tv = total_stock_value_by_supplier(df)
                st.metric("Valeur Totale Globale du Stock", f"{df_tv['Valeur Totale HT'].sum():,.2f} €".replace(",", " "))
                st.dataframe(df_tv, use_container_width=True)

            with tab7:
                display_stock_by_family(df)

            with tab8:
                st.subheader("Analyse de la profondeur de gamme (Chaussures)")
                display_specific_designations(df.copy())

    except Exception as e:
        st.error(f"Impossible de traiter ce fichier stock : {str(e)}")


else:
    st.info("Utilisez la barre latérale pour charger un fichier stock pour commencer.")
