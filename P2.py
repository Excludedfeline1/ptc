import requests
import streamlit as st
import pandas as pd
import os
import json
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from collections import Counter
import plotly.graph_objects as go

if "team" not in st.session_state:
    st.session_state.team = []

if "removed_pokemon" not in st.session_state:
    st.session_state.removed_pokemon = False

if "team_loaded" not in st.session_state:
    st.session_state.team_loaded = False

url = "https://pokeapi.co/api/v2/"

st.header("Regional Pokemon Team Builder")

DATA_FOLDER = "data"
os.makedirs(DATA_FOLDER, exist_ok=True)

TEAM_CSV = os.path.join(DATA_FOLDER, "team.csv")

TYPE_COLORS = {
    "Normal": "#A8A878", "Fire": "#F08030", "Water": "#6890F0", "Electric": "#F8D030",
    "Grass": "#78C850", "Ice": "#98D8D8", "Fighting": "#C03028", "Poison": "#A040A0",
    "Ground": "#E0C068", "Flying": "#A890F0", "Psychic": "#F85888", "Bug": "#A8B820",
    "Rock": "#B8A038", "Ghost": "#705898", "Dragon": "#7038F8", "Dark": "#705848",
    "Steel": "#B8B8D0", "Fairy": "#EE99AC"
}

def save_team_to_csv(poke_entry):
    if "team" not in st.session_state:
        st.session_state["team"] = []
    if len(st.session_state["team"]) >= 6:
        return False
    st.session_state["team"].append(poke_entry)
    return True

def remove_from_team(pokemon_data):
    st.session_state.team = [p for p in st.session_state.team if p["Name"] != pokemon_data["Name"]]
    pd.DataFrame(st.session_state.team).to_csv(TEAM_CSV, index=False)

def display_team():
    if "team" not in st.session_state or not st.session_state["team"]:
        st.info("Your team is currently empty.")
        return

    st.subheader("My Team:")

    cols = st.columns(3)

    for i, poke in enumerate(st.session_state["team"]):
        with cols[i % 3]:
            st.markdown(f"### {poke['Name']}")
            st.markdown("**Types:** " + ', '.join(poke['Types'].title().split(", ")))

            if st.button("❌ Remove", key=f"remove_{i}"):
                st.session_state["team"].pop(i)
                st.rerun()
            info = get_pokemon_info(poke["API Name"])
            st.image(info["sprites"]["front_default"])
    return True


def load_team():
    if not st.session_state.team_loaded:
        if os.path.isfile(TEAM_CSV) and os.path.getsize(TEAM_CSV) > 0:
            try:
                df = pd.read_csv(TEAM_CSV)
                st.session_state.team = df.to_dict(orient="records")
            except pd.errors.EmptyDataError:
                st.warning("Your team file exists but is empty. Starting with a fresh team.")
        st.session_state.team_loaded = True

@st.cache_data
def get_pokemon_info(selected_pokemon):
    return requests.get(f"{url}/pokemon/{selected_pokemon}").json()

@st.cache_data
def get_default_variant(species_name):
    try:
        data = requests.get(f"{url}/pokemon-species/{species_name}").json()
        for variety in data['varieties']:
            if variety['is_default']:
                return variety['pokemon']['name']
    except:
        pass
    return None

@st.cache_data
def generate_list_of_native_pokemon(region_selected):
    cache_file = os.path.join(DATA_FOLDER, f"native_{region_selected.lower()}.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            return json.load(f)

    region_data = requests.get(f"{url}/region/{region_selected.lower()}").json()
    pokedex_url = region_data['pokedexes'][0]['url']
    pokedex_data = requests.get(pokedex_url).json()

    entries = pokedex_data['pokemon_entries']
    species_names = [(entry['entry_number'], entry['pokemon_species']['name']) for entry in entries]

    with ThreadPoolExecutor() as executor:
        results = list(executor.map(lambda x: get_default_variant(x[1]), species_names))
        final_list = [res for res in results if res]

    with open(cache_file, "w") as f:
        json.dump(final_list, f)

    return final_list


@st.cache_data
def generate_new_pokemon_from_region(region_selected):
    cache_file = os.path.join(DATA_FOLDER, f"new_{region_selected.lower()}.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            return json.load(f)

    region_to_generation = {
        "Kanto": 1, "Johto": 2, "Hoenn": 3, "Sinnoh": 4,
        "Unova": 5, "Kalos": 6, "Alola": 7, "Galar": 8, "Paldea": 9, "Hisui": 8
    }

    region_keywords = {
        "Alola": "alola",
        "Galar": "galar",
        "Hisui": "hisui",
        "Paldea": "paldea"
    }

    gen_number = region_to_generation.get(region_selected)
    if gen_number is None:
        return []

    gen_data = requests.get(f"{url}/generation/{gen_number}").json()
    species_list = gen_data['pokemon_species']
    species_names = [s["name"] for s in species_list]

    native_names = []

    if region_selected in region_keywords:
        region_data = requests.get(f"{url}/region/{region_selected.lower()}").json()
        pokedex_url = region_data['pokedexes'][0]['url']
        pokedex_data = requests.get(pokedex_url).json()
        entries = pokedex_data['pokemon_entries']
        species_urls = [entry['pokemon_species']['url'] for entry in entries]

        def get_regional_variant(species_url):
            try:
                info = requests.get(species_url).json()
                for v in info['varieties']:
                    if region_keywords[region_selected] in v['pokemon']['name']:
                        return v['pokemon']['name']
            except:
                return None

        with ThreadPoolExecutor() as executor:
            variant_results = list(executor.map(get_regional_variant, species_urls))
            native_names.extend([res for res in variant_results if res])

    native_names.extend(species_names)
    native_names = list(set(native_names))

    with open(cache_file, "w") as f:
        json.dump(native_names, f)

    return native_names


@lru_cache(maxsize=None)
def get_pokemon_id(name):
    try:
        return get_pokemon_info(name)["id"]
    except:
        return float('inf')


def get_all_forms(name):
    try:
        species_data = requests.get(f"{url}/pokemon-species/{name}").json()
        varieties = species_data.get("varieties", [])
        form_list = []
        form_labels = []
        region_keywords = ("alola", "galar", "hisui", "paldea")
        sp_form = ("mega", "gmax")
        s_pokemon = ("pikachu", "eevee")

        for variety in varieties:
            form_name = variety['pokemon']['name']
            is_default = variety['is_default']

            if name in s_pokemon:
                if not any(tag in form_name for tag in sp_form) and not is_default:
                    continue
            else:
                if any(region in form_name for region in region_keywords):
                    continue

            form_list.append(form_name)

            if is_default:
                form_data = requests.get(f"{url}/pokemon/{form_name}").json()
                proper_name = form_data['forms'][0]['name'].replace("-", " ").title()
                form_labels.append(proper_name)
            else:
                form_labels.append(format_pokemon_name(form_name))

        default_names = [
            requests.get(f"{url}/pokemon/{f}").json()['forms'][0]['name'].replace("-", " ").title()
            for f in form_list
        ]
        if any(label in default_names for label in form_labels):
            default_index = form_labels.index(
                next(label for label in form_labels if label in default_names)
            )
            form_labels.insert(0, form_labels.pop(default_index))
            form_list.insert(0, form_list.pop(default_index))

        return form_list, form_labels
    except Exception as e:
        st.error(f"Error fetching forms: {e}")
        return [name], ["Default"]




def format_pokemon_name(raw_name):
    special_cases = {
        "mr-mime": "Mr. Mime", "mime-jr": "Mime Jr.","mr-rime": "Mr. Rime", "type-null": "Type: Null",
        "jangmo-o": "Jangmo-o", "hakamo-o": "Hakamo-o", "kommo-o": "Kommo-o",
        "porygon-z": "Porygon-Z", "ho-oh": "Ho-Oh", "tapu-koko": "Tapu Koko",
        "tapu-lele": "Tapu Lele", "tapu-bulu": "Tapu Bulu", "tapu-fini": "Tapu Fini",
        "flabebe": "Flabébé", "nidoran-f": "Nidoran♀", "nidoran-m": "Nidoran♂"
    }
    r_variants = {
        "alola" : "Alolan",
        "galar": "Galarian",
        "hisui": "Hisuian",
        "paldea" : "Paldean"
    }
    raw_name = raw_name.lower()
    for region, prefix in r_variants.items():
        if raw_name.endswith(f"-{region}"):
            base_name = raw_name.rsplit(f"-{region}", 1)[0]
            formatted_base = special_cases.get(base_name, ' '.join(part.capitalize() for part in base_name.split('-')))
            return f"{prefix} {formatted_base}"
    if raw_name in special_cases:
        return special_cases[raw_name]
    parts = raw_name.replace('-', ' ').split()
    capitalized = [part.capitalize() for part in parts]
    return ' '.join(capitalized)


def get_learnable_moves(pokemon_name):
    url = f"https://pokeapi.co/api/v2/pokemon/{pokemon_name.lower()}"
    response = requests.get(url)

    if response.status_code != 200:
        st.error(f"Failed to fetch moves for {pokemon_name}. API returned status code {response.status_code}.")
        return []

    try:
        data = response.json()
        return data['moves']
    except Exception as e:
        st.error(f"Error parsing JSON for {pokemon_name}: {e}")
        return []


def get_move_details(move_url):
    move_response = requests.get(move_url)
    move_data = move_response.json()
    return {
        "name": move_data["name"].replace('-', ' ').title(),
        "type": move_data["type"]["name"].title(),
        "category": move_data["damage_class"]["name"].title(),
        "power": move_data["power"],
        "accuracy": move_data["accuracy"],
        "pp": move_data["pp"]
    }

def display_moves(moves):
    df = pd.DataFrame(moves)
    st.dataframe(df, use_container_width=True)

def show_stat_radar_table(selected_form_name):

    stat_url = f"{url}/pokemon/{selected_form_name}"
    response = requests.get(stat_url)
    if response.status_code != 200:
        st.error(f"Failed to fetch stats for {selected_form_name}")
        return

    pokemon_data = response.json()

    keys = ["hp", "attack", "defense", "speed", "special-defense", "special-attack"]
    stat_labels = ["HP", "Attack", "Defense", "Speed", "Sp. Def", "Sp. Atk"]

    stats = {s["stat"]["name"]: s["base_stat"] for s in pokemon_data["stats"]}
    values = [stats[k] for k in keys]

    labels_with_values = [f"{label} {val}" for label, val in zip(stat_labels, values)]

    values.append(values[0])
    labels_with_values.append(labels_with_values[0])

    fig = go.Figure(
        data=[
            go.Scatterpolar(
                r=values,
                theta=labels_with_values,
                fill='toself',
                line=dict(shape='linear'),
                name=selected_form_name.capitalize()
            )
        ],
        layout=go.Layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 255],
                    tickangle=45
                ),
                angularaxis=dict(
                    rotation=90,
                    direction="clockwise"
                ),
                gridshape = "linear"
            ),
            showlegend=False,
            margin=dict(t=30, b=30),
            dragmode=False
        )
    )

    config = {
        "staticPlot": True,
        "displayModeBar": False
    }

    df = pd.DataFrame(stats.items(), columns=["Stat", "Value"])

    total = df["Value"].sum()
    df.loc[len(df.index)] = ["Total", total]

    def color_gradient(val):
        if val == "Total":
            return "background-color: lightgray; font-weight: bold;"
        if isinstance(val, int):
            color = f"hsl({(val / 255) * 120}, 75%, 60%)"
            return f"background-color: {color};"
        return ""

    styled_df = df.style.applymap(color_gradient, subset=["Value"]) \
        .set_properties(**{"text-align": "center"}) \
        .set_table_styles([{
        'selector': 'th',
        'props': [('text-align', 'center')]
    }])

    col1, col2 = st.columns([2, 1])
    with col1:
        st.plotly_chart(fig, use_container_width=True, config=config)
    with col2:
        st.markdown("<div style='margin-top: 75px;'></div>", unsafe_allow_html=True)
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

def display_pokemon_info(name):
    form_list, form_labels = get_all_forms(name)

    col1, col2 = st.columns([2, 3])

    if len(form_list) > 1:
        with col2:
            selected_label = st.radio("Forms", form_labels, label_visibility="collapsed")
            selected_index = form_labels.index(selected_label)
            selected_form = form_list[selected_index]
    else:
        selected_form = form_list[0]

    with col1:
        poke_info_data = get_pokemon_info(selected_form)
        sprite_url = poke_info_data["sprites"]["front_default"]
        display_name = format_pokemon_name(selected_form)
        types = [t["type"]["name"].capitalize() for t in poke_info_data["types"]]
        abilities = [a["ability"]["name"].replace("-", " ").title() for a in poke_info_data["abilities"] if not a["is_hidden"]]
        hidden_abilities = [a["ability"]["name"].replace("-", " ").title() for a in poke_info_data["abilities"] if a["is_hidden"]]

        st.image(sprite_url, width=160)

        st.markdown(f"### {display_name}")
        st.markdown("**Types:** " + ' '.join([
            f'<span style="background-color:{TYPE_COLORS.get(t, "#DDD")};color:white;padding:4px;border-radius:4px">{t}</span>'
            for t in types
        ]), unsafe_allow_html=True)
        st.markdown(f"**Abilities:** {', '.join(abilities)}")
        if hidden_abilities:
            st.markdown("**Hidden Abilities:** " + ", ".join(hidden_abilities))

    additional_info = st.tabs(["Basic Info Only", "Learnable Moves", "Stat-Distribution"])
    with additional_info[1]:
        st.subheader("Learnable Moves")
        with st.spinner("Fetching moves..."):
            if "mega" in selected_form.lower() or "gmax" in selected_form.lower():
                move_source = name
            else:
                move_source = selected_form
            raw_moves = get_learnable_moves(move_source)

            moves = []
            for m in raw_moves:
                for detail in m["version_group_details"]:
                    if detail["move_learn_method"]["name"] == "level-up":
                        move_info = get_move_details(m["move"]["url"])
                        moves.append(move_info)
                        break

            display_moves(moves)
    with additional_info[2]:
        show_stat_radar_table(selected_form)

    return selected_form

nav = st.sidebar.selectbox("What would you like to do?", options=["Introduction", "Create a Team", "View Teams"])

if nav == "Introduction":
    st.subheader("Welcome!")
    st.markdown("""
    This tool helps you build your dream Pokémon team by selecting native Pokémon from different regions.
    Use the sidebar to start building your team or view/export your current lineup.
    
    **IMPORTANT NOTE: On first load of each list, please be aware there is a slight delay as it generates the list. This is only an issue on first use!**
    """)
    consent = st.checkbox("Check this box if you would like to see a map of Gamefreak headquarters. (I had no idea how to include a map with pokemon forgive me pls)")
    color = st.color_picker("Pick a your favorite color (will change map dot color)")
    df = pd.DataFrame({
        "lat": [35.6528],
        "lon": [139.6917]
    })
    if st.button("Confirm"):
        if consent:
            st.success("Map created successfully")
            st.map(df, zoom = 13, color = color)
        else:
            st.info("Please select the checkbox to view the map, otherwise please ignore this message and proceed to team creation.")

elif nav == "Create a Team":
    load_team()
    region_list = ["Kanto", "Johto", "Hoenn", "Sinnoh", "Unova", "Kalos", "Alola", "Galar", "Paldea"]
    region_selected = st.selectbox("Select a region", options=region_list)

    if region_selected:
        new_pokemon_only = st.radio("Show only newly introduced Pokémon?", options=["Yes", "No"])
        sort_order = st.radio("Sort by:", options=["Numerical", "Alphabetical"])

        if new_pokemon_only == "Yes":
            natives_list = generate_new_pokemon_from_region(region_selected)
        else:
            natives_list = generate_list_of_native_pokemon(region_selected)

        if sort_order == "Alphabetical":
            natives_list.sort()
        else:
            with ThreadPoolExecutor() as executor:
                pokemon_with_ids = list(executor.map(lambda name: (name, get_pokemon_id(name)), natives_list))
            pokemon_with_ids.sort(key=lambda x: x[1])
            natives_list = [name for name, _ in pokemon_with_ids]

        display_natives_list = [""] + [format_pokemon_name(p) for p in natives_list]
        native_selected = st.selectbox("Choose a native Pokémon", options=display_natives_list)

        if native_selected:
            native_index = display_natives_list.index(native_selected) - 1
            native_api_name = natives_list[native_index]
            st.header(native_selected)
            current_form_name = display_pokemon_info(native_api_name)
            current_form_data = get_pokemon_info(current_form_name)
            col1, col2, col3 = st.columns([2, 2, 1])
            s_f = None
            att = False
            with col2:
                if st.button("Add to My Team"):
                    att =True
                    s_f = save_team_to_csv({
                        "Name": format_pokemon_name(current_form_name),
                        "API Name": current_form_name,
                        "Types": ', '.join([t["type"]["name"] for t in current_form_data["types"]])
                    })

            if att and s_f:
                st.success(f"{native_selected} has been added to the team!")
                att = False
            elif att and not s_f:
                st.warning("You can only have up to 6 Pokémon.")
                att = False

            display_team()
elif nav == "View Teams":


    if display_team():
        if st.button("🗑️ Clear Entire Team"):
            st.session_state.team = []
            if os.path.exists(TEAM_CSV):
                os.remove(TEAM_CSV)
            st.rerun()

    all_types = []
    for pokemon in st.session_state.team:
        types = pokemon["Types"].split(", ")
        all_types.extend(types)

    if all_types:
        type_counts = Counter(all_types)
        types = list(type_counts.keys())
        counts = [type_counts[t] for t in types]
        colors = [TYPE_COLORS.get(t.capitalize(), "#DDDDDD") for t in types]

        fig = go.Figure(data=[
            go.Bar(
                x=types,
                y=counts,
                marker_color=colors,
                text=counts,
                textposition="auto"
            )
        ])
        fig.update_layout(
            title="Team Type Distribution",
            xaxis_title="Type",
            yaxis_title="Count",
            yaxis=dict(tickformat=",d"),
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No Pokémon types to show in the chart. Add some to your team!")
