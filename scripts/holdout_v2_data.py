"""Fixture data for the holdout_v2 positive-case dataset.

Ten original settings, each carrying a StoryBrief, a World, a CharacterSet and a
Storyboard that satisfy the deterministic validators in
``fictionforge.guardrails.validators``.  No setting, name or passage is reused
from the dev or holdout fixtures.
"""

SETTINGS = [
    # ------------------------------------------------------------------
    # 1. Solarpunk lagoon city
    # ------------------------------------------------------------------
    {
        "num": 1,
        "slug": "solarpunk_tidal_conservatories",
        "gen_name": "v2_01_solarpunk_tidal_conservatories",
        "evidence_summary": "The world, cast and storyboard satisfy the brief's tide-powered solarpunk setting; deterministic validators are clean and there are no blocking defects.",
        "brief": {
            "title": "The Glass Tide",
            "premise": "A junior tide-warden discovers that the lagoon gates are silting shut weeks ahead of schedule, and must convince the guilds to halt the glassblowing season before the city loses the tide that powers it.",
            "genre": "solarpunk",
            "tone": "hopeful",
            "target_audience": "adult",
            "location_count": 4,
            "constraints": [
                "forbid:dragon",
                "require:tide",
                "No combustion engines or fossil fuels anywhere in the setting.",
                "max_locations:6",
            ],
        },
        "world": {
            "world_id": "wld_tidal_conservatories",
            "name": "The Tidal Conservatories",
            "description": "A terraced city grown into a shallow lagoon, where mangrove walls, vitrified glass locks and tide-mills turn the twice-daily flood into power, food and light.",
            "locations": [
                {"id": "loc_glassgate_locks", "name": "The Glassgate Locks", "description": "Vitrified gates that meter the tide into the lagoon; their sills are silting up weeks ahead of the survey."},
                {"id": "loc_mangrove_terraces", "name": "The Mangrove Terraces", "description": "Stepped root-gardens where families tend silt-traps and grow the city's rice and reed stock."},
                {"id": "loc_algae_fields", "name": "The Algae Fields", "description": "Raft-farms of oil algae that feed the kiln digesters and the lamp vats."},
                {"id": "loc_bellmakers_quay", "name": "Bellmaker's Quay", "description": "The wharf where channel bells and glass floats are cast, and the seat of the glassblower guilds."},
            ],
            "factions": [
                {"id": "fac_tide_wardens", "name": "The Tide Wardens", "description": "Engineers sworn to keep the locks clear and read the tide tables for the whole lagoon.", "location_ids": ["loc_glassgate_locks"]},
                {"id": "fac_glassblower_guild", "name": "The Glassblower Guild", "description": "Artisans who fire their kilns on lagoon gas and hold the charter for every bell and window.", "location_ids": ["loc_bellmakers_quay"]},
                {"id": "fac_ferry_cooperative", "name": "The Ferry Cooperative", "description": "Sail and paddle barge crews who haul harvest, glass and dredged silt across the lagoon.", "location_ids": ["loc_algae_fields"]},
            ],
            "rules": [
                {"id": "rul_tide_power", "statement": "All power in the city comes from the tide, the sun or the algae digesters; combustion engines are banned by charter.", "category": "technology"},
                {"id": "rul_lock_oath", "statement": "Every gate crew must clear its lock before each spring tide, whatever the guild calendar says.", "category": "social"},
                {"id": "rul_bell_code", "statement": "A channel bell cast out of tune must be recast within a day, because the whole lagoon navigates by its ring.", "category": "social"},
                {"id": "rul_silt_debt", "statement": "Whoever dredges silt from the locks owns the fertile silt, but must spread it on the terraces within a season.", "category": "social"},
            ],
            "history": [
                {"id": "evt_gates_raised", "name": "The Raising of the Glassgates", "era": "The Founding Tides", "description": "The first locks were fused from lagoon glass so the tide could be let in without drowning the terraces.", "location_ids": ["loc_glassgate_locks"]},
                {"id": "evt_great_silting", "name": "The Great Silting", "era": "The Lean Years", "description": "A storm choked the gates with silt; the city went hungry until the terraces dug the locks out.", "location_ids": ["loc_glassgate_locks", "loc_mangrove_terraces"]},
                {"id": "evt_bell_charter", "name": "The Bell Charter", "era": "The Lean Years", "description": "After a night collision in fog, the guilds bound themselves to recast any mistuned channel bell within a day.", "location_ids": ["loc_bellmakers_quay"]},
            ],
            "conflicts": [
                {"id": "cnf_kiln_calendar", "name": "The Kiln Calendar", "description": "The Glassblower Guild wants a long firing season, but the Tide Wardens need the gates shut for dredging before the spring tide.", "faction_ids": ["fac_glassblower_guild", "fac_tide_wardens"]},
                {"id": "cnf_silt_rights", "name": "The Silt Rights", "description": "The Ferry Cooperative claims the rich silt it dredges, while the Tide Wardens say it belongs to the terrace commons.", "faction_ids": ["fac_ferry_cooperative", "fac_tide_wardens"]},
            ],
        },
        "characters": {
            "world_id": "wld_tidal_conservatories",
            "characters": [
                {
                    "id": "chr_mara_ilek", "name": "Mara Ilek", "role": "protagonist",
                    "description": "A junior tide-warden who keeps the sounding poles at the Glassgate Locks and still writes her survey notes in her mother's hand.",
                    "personality_traits": ["precise", "quietly stubborn", "dutiful"],
                    "motivation": "To prove the locks are silting early, before the city loses the tide it runs on.",
                    "goal": "Get the gates dredged before the spring tide arrives.",
                    "flaw": "She assumes the soundings will persuade people by themselves.",
                    "internal_conflict": "She fears becoming the alarmist the guilds once called her mother.",
                    "external_conflict": "The guild masters refuse to shorten the firing season for a junior warden's numbers.",
                    "home_location_id": "loc_glassgate_locks", "faction_id": "fac_tide_wardens",
                    "abilities": [{"name": "Silt-reading", "description": "Reads the settle lines on a sounding pole to judge how fast a channel is filling.", "category": "mental"}],
                    "arc": "Mara learns to carry her proof into the guild halls and let others help her hold the gate.",
                },
                {
                    "id": "chr_oren_pell", "name": "Oren Pell", "role": "antagonist",
                    "description": "Master of the Glassblower Guild, whose kilns keep half the quay employed and whose word sets the firing calendar.",
                    "personality_traits": ["commanding", "pragmatic", "proud"],
                    "motivation": "To protect the firing season his guild's families depend on.",
                    "goal": "Keep the locks open through the full firing season.",
                    "flaw": "He cannot admit a trade-off once he has made it.",
                    "internal_conflict": "He has read the same tide tables as Mara and knows what they say.",
                    "external_conflict": "Mara's soundings prove the silting is early, and the wardens want the gates closed.",
                    "home_location_id": "loc_bellmakers_quay", "faction_id": "fac_glassblower_guild",
                    "abilities": [{"name": "Furnace-sense", "description": "Judges a kiln's heat and temper by the sound of its draw.", "category": "mental"}],
                    "arc": "Pell must choose between the guild's season and the lagoon that feeds it.",
                },
                {
                    "id": "chr_sana_duro", "name": "Sana Duro", "role": "supporting",
                    "description": "A cooperative barge pilot who hauls algae and dredged silt between the fields and the terraces.",
                    "personality_traits": ["sharp", "loyal", "mercurial"],
                    "motivation": "To keep the Ferry Cooperative solvent and fairly paid.",
                    "goal": "Win the dredging contract without selling the cooperative's silt rights.",
                    "flaw": "She bargains when she should listen.",
                    "internal_conflict": "She wants the wardens' contract but distrusts their charter.",
                    "external_conflict": "Both the wardens and the guild want her barge and her silence.",
                    "home_location_id": "loc_algae_fields", "faction_id": "fac_ferry_cooperative",
                    "abilities": [{"name": "Channel-reading", "description": "Feels a channel's depth through the barge's tiller in fog or darkness.", "category": "physical"}],
                    "arc": "Sana stakes her barge on the wardens' evidence and drags the truth into the open.",
                },
            ],
            "relationships": [
                {"id": "rel_mara_sana", "source_character_id": "chr_mara_ilek", "target_character_id": "chr_sana_duro", "relationship_type": "ally", "description": "Mara hires Sana's barge to sound the gate channels.", "conflict": "Sana's price is a say in who owns the dredged silt."},
                {"id": "rel_mara_oren", "source_character_id": "chr_mara_ilek", "target_character_id": "chr_oren_pell", "relationship_type": "opponent", "description": "Pell dismissed Mara's soundings as apprentice work.", "conflict": "His guild cannot afford the closure she demands."},
            ],
        },
        "storyboard": {
            "world_id": "wld_tidal_conservatories",
            "title": "The Glass Tide",
            "logline": "A junior tide-warden proves the lagoon gates are silting early and forces the guilds to choose between the firing season and the tide.",
            "theme": "commons and the cost of proof",
            "acts": [
                {
                    "id": "act_setup", "title": "Setup", "purpose": "setup",
                    "scenes": [
                        {"id": "scn_tide_tables", "title": "The Soundings", "summary": "Mara reads the settle lines at the Glassgate Locks and finds the sills silting weeks ahead of the survey.", "location_id": "loc_glassgate_locks", "character_ids": ["chr_mara_ilek"], "goal": "Confirm the silting rate.", "conflict": "The numbers contradict the guild calendar.", "outcome": "Mara certifies the early silting in the wardens' log.", "depends_on": []},
                        {"id": "scn_quay_warning", "title": "The Guild's Answer", "summary": "Mara takes the soundings to Bellmaker's Quay, where Oren Pell dismisses them as apprentice work and refuses to shorten the firing season.", "location_id": "loc_bellmakers_quay", "character_ids": ["chr_mara_ilek", "chr_oren_pell"], "goal": "Win a dredging order.", "conflict": "Pell will not trade the guild's season for a junior warden's numbers.", "outcome": "The petition is refused; Mara must find another lever.", "depends_on": ["scn_tide_tables"]},
                    ],
                },
                {
                    "id": "act_rising", "title": "Rising Action", "purpose": "rising_action",
                    "scenes": [
                        {"id": "scn_ferry_bargain", "title": "The Barge Charter", "summary": "Mara charters Sana's barge at the Algae Fields to run a full channel sounding the guild cannot dispute.", "location_id": "loc_algae_fields", "character_ids": ["chr_mara_ilek", "chr_sana_duro"], "goal": "Gather indisputable soundings.", "conflict": "Sana demands a voice in the silt rights for her help.", "outcome": "Sana signs on; the sounding begins at the next ebb.", "depends_on": ["scn_quay_warning"]},
                        {"id": "scn_silt_proof", "title": "Two Fingers of Water", "summary": "The channel survey proves the locks will shoal shut before the firing season ends, days ahead of the spring tide.", "location_id": "loc_glassgate_locks", "character_ids": ["chr_mara_ilek", "chr_sana_duro"], "goal": "Prove the closure date.", "conflict": "The proof means the season must end early.", "outcome": "The survey is witnessed and logged beyond dispute.", "depends_on": ["scn_ferry_bargain"]},
                    ],
                },
                {
                    "id": "act_climax", "title": "Climax", "purpose": "climax",
                    "scenes": [
                        {"id": "scn_bell_muster", "title": "The Muster Bell", "summary": "Mara rings the muster bell at the Quay to force a guild vote; as the masters argue, the ebb itself strands a kiln barge, and Pell concedes.", "location_id": "loc_bellmakers_quay", "character_ids": ["chr_mara_ilek", "chr_oren_pell", "chr_sana_duro"], "goal": "Force the dredging vote.", "conflict": "Pell stakes his mastership on the season holding.", "outcome": "The guild votes to dredge; the season is shortened, not lost.", "depends_on": ["scn_silt_proof"]},
                    ],
                },
                {
                    "id": "act_resolution", "title": "Resolution", "purpose": "resolution",
                    "scenes": [
                        {"id": "scn_shared_dredging", "title": "Silt on the Terraces", "summary": "Guild crews and the cooperative dredge the locks together, and the rich silt is spread on the Mangrove Terraces under a shared charter.", "location_id": "loc_mangrove_terraces", "character_ids": ["chr_mara_ilek", "chr_sana_duro", "chr_oren_pell"], "goal": "Clear the locks before the spring tide.", "conflict": "The silt rights must be shared without a new quarrel.", "outcome": "The gates clear in time; the silt feeds the terraces and the charter is amended.", "depends_on": ["scn_bell_muster"]},
                    ],
                },
            ],
        },
    },
    # ------------------------------------------------------------------
    # 2. Wuxia fantasy coast
    # ------------------------------------------------------------------
    {
        "num": 2,
        "slug": "wuxia_crane_banner_coast",
        "gen_name": "v2_02_wuxia_crane_banner_coast",
        "evidence_summary": "The world, cast and storyboard satisfy the brief's crane-and-covenant wuxia setting; deterministic validators are clean and there are no blocking defects.",
        "brief": {
            "title": "Feathers Over the Mist",
            "premise": "A disowned sword-student must carry her late master's tally-stick to three rival sects to call a peace moot, before the island clans' feud burns the last crane rookeries.",
            "genre": "wuxia fantasy",
            "tone": "lyrical",
            "target_audience": "adult",
            "location_count": 4,
            "constraints": [
                "forbid:gunpowder",
                "require:crane",
                "Duels are settled by formal challenge, never ambush.",
                "max_locations:6",
            ],
        },
        "world": {
            "world_id": "wld_crane_banner_coast",
            "name": "The Crane Banner Coast",
            "description": "A mist-bound coast of rocky islets where martial sects hold fishing rights under an old dueling covenant, and the cranes that nest in the rookeries are counted as omens by every school.",
            "locations": [
                {"id": "loc_mist_rookery", "name": "The Mist Rookery", "description": "Crane nesting islets whose shallows hold the richest eel grounds on the coast."},
                {"id": "loc_bannerhall", "name": "Bannerhall", "description": "The hall where challenges are recorded beneath the Crane Banner pact."},
                {"id": "loc_saltmarket_isle", "name": "Saltmarket Isle", "description": "A neutral trade isle where envoys may meet under the market peace."},
                {"id": "loc_thunder_reed_dojo", "name": "Thunder Reed Dojo", "description": "A weathered school built in the reed marshes, where the tally-stick's late keeper taught."},
            ],
            "factions": [
                {"id": "fac_crane_sect", "name": "The Crane Sect", "description": "Keepers of the dueling covenant, who witness every formal challenge at Bannerhall.", "location_ids": ["loc_bannerhall"]},
                {"id": "fac_eel_school", "name": "The Eel School", "description": "An aggressive school claiming ancestral fishing rights to the rookery shallows.", "location_ids": ["loc_mist_rookery"]},
                {"id": "fac_salt_wardens", "name": "The Salt Wardens", "description": "Neutral market wardens who guarantee safe conduct for envoys on Saltmarket Isle.", "location_ids": ["loc_saltmarket_isle"]},
            ],
            "rules": [
                {"id": "rul_challenge", "statement": "No blade may be drawn between sects except after a formal challenge witnessed at Bannerhall.", "category": "social"},
                {"id": "rul_rookery", "statement": "No nets may be cast within sight of the Mist Rookery while the cranes are nesting.", "category": "social"},
                {"id": "rul_tally", "statement": "A master's tally-stick, once presented, obliges every sect named on it to send an envoy to the moot.", "category": "social"},
                {"id": "rul_light_body", "statement": "The light-body art lets a trained adept run across reeds, rigging and rooftops, but never over open water.", "category": "metaphysics"},
            ],
            "history": [
                {"id": "evt_net_wars", "name": "The Net Wars", "era": "The Hungry Years", "description": "Sects feuded over the rookery shallows until the eel grounds were nearly fished out.", "location_ids": ["loc_mist_rookery"]},
                {"id": "evt_broken_challenge", "name": "The Broken Challenge", "era": "The Hungry Years", "description": "An ambush disguised as a formal duel nearly destroyed the covenant and the market peace.", "location_ids": ["loc_saltmarket_isle"]},
                {"id": "evt_first_banner", "name": "The First Banner", "era": "The Gathering", "description": "The sects swore the Crane Banner pact at Bannerhall and ended the Net Wars.", "location_ids": ["loc_bannerhall"]},
            ],
            "conflicts": [
                {"id": "cnf_rookery_rights", "name": "The Rookery Rights", "description": "The Eel School presses its claim to fish the rookery shallows while the Crane Sect holds the nesting ban.", "faction_ids": ["fac_eel_school", "fac_crane_sect"]},
                {"id": "cnf_unanswered_tally", "name": "The Unanswered Tally", "description": "The sects are deadlocked over whether a tally-stick carried by a disowned student still binds them.", "faction_ids": ["fac_crane_sect", "fac_eel_school"]},
            ],
        },
        "characters": {
            "world_id": "wld_crane_banner_coast",
            "characters": [
                {
                    "id": "chr_lin_wei", "name": "Lin Wei", "role": "protagonist",
                    "description": "A disowned sword-student of the Crane Sect, carrying the tally-stick her dying master cut for the peace moot.",
                    "personality_traits": ["resolute", "self-effacing", "watchful"],
                    "motivation": "To honour her master's last order and see the peace moot held.",
                    "goal": "Deliver the tally-stick to the three named sects before midsummer.",
                    "flaw": "Shame makes her hide her disowning, even from allies.",
                    "internal_conflict": "She believes she failed her master, though she kept every vow.",
                    "external_conflict": "The Eel School calls her tally void because she is disowned.",
                    "home_location_id": "loc_bannerhall", "faction_id": "fac_crane_sect",
                    "abilities": [{"name": "Reed-step", "description": "Runs across reeds and rigging by the light-body art, in keeping with the covenant's limits.", "category": "physical"}],
                    "arc": "Lin Wei stops hiding her disowning and lets the tally speak for itself.",
                },
                {
                    "id": "chr_gao_ren", "name": "Gao Ren", "role": "antagonist",
                    "description": "Senior brother of the Eel School, a hard pragmatist whose school has gone hungry under the nesting ban.",
                    "personality_traits": ["unyielding", "proud", "dutiful"],
                    "motivation": "To win the rookery fishing rights his school needs to survive.",
                    "goal": "Discredit the tally-stick and void the moot.",
                    "flaw": "He calls his pride pragmatism.",
                    "internal_conflict": "He respects the covenant he is trying to bend.",
                    "external_conflict": "Lin Wei's tally, if honoured, calls a moot that could codify the ban forever.",
                    "home_location_id": "loc_mist_rookery", "faction_id": "fac_eel_school",
                    "abilities": [{"name": "Eel-form grip", "description": "A wrestling style that turns an opponent's balance against them on wet ground.", "category": "physical"}],
                    "arc": "Gao Ren must decide whether a lawful loss is worth more than a starving victory.",
                },
                {
                    "id": "chr_mei_sura", "name": "Mei Sura", "role": "supporting",
                    "description": "A Salt Warden clerk on Saltmarket Isle who registers challenges and keeps the market's envoys' book.",
                    "personality_traits": ["precise", "cautious", "dry-humoured"],
                    "motivation": "To keep Saltmarket neutral and the moot lawful.",
                    "goal": "See the moot convened on her isle, under the market peace.",
                    "flaw": "She hedges every promise until the cost of honesty is clear.",
                    "internal_conflict": "Her neutrality protects the market but starves her of conviction.",
                    "external_conflict": "Both sects pressure her to mislay or hasten filings.",
                    "home_location_id": "loc_saltmarket_isle", "faction_id": "fac_salt_wardens",
                    "abilities": [{"name": "Covenant recall", "description": "Recites the pact and its precedents from memory, word for word.", "category": "mental"}],
                    "arc": "Mei Sura finally stakes her neutrality on the side of the tally.",
                },
            ],
            "relationships": [
                {"id": "rel_lin_gao", "source_character_id": "chr_lin_wei", "target_character_id": "chr_gao_ren", "relationship_type": "rival", "description": "Gao Ren challenged Lin Wei's right to carry the tally.", "conflict": "Each believes the other's sect is breaking the covenant."},
                {"id": "rel_lin_mei", "source_character_id": "chr_lin_wei", "target_character_id": "chr_mei_sura", "relationship_type": "ally", "description": "Mei Sura registers Lin Wei's tally over Eel School objections.", "conflict": None},
            ],
        },
        "storyboard": {
            "world_id": "wld_crane_banner_coast",
            "title": "Feathers Over the Mist",
            "logline": "A disowned sword-student carries her master's tally-stick across the mist coast to convene the moot that decides the rookeries' fate.",
            "theme": "honour without standing",
            "acts": [
                {
                    "id": "act_setup", "title": "Setup", "purpose": "setup",
                    "scenes": [
                        {"id": "scn_masters_tally", "title": "The Master's Tally", "summary": "Lin Wei receives the tally-stick at Thunder Reed Dojo from her dying master, who names three sects to summon.", "location_id": "loc_thunder_reed_dojo", "character_ids": ["chr_lin_wei"], "goal": "Take up the tally.", "conflict": "Accepting it declares her disowning to every sect.", "outcome": "She swears to deliver it and sets out for Bannerhall.", "depends_on": []},
                        {"id": "scn_challenge_posted", "title": "The Counter-Challenge", "summary": "At Bannerhall, Gao Ren posts a counter-challenge naming Lin Wei's tally void because she is disowned.", "location_id": "loc_bannerhall", "character_ids": ["chr_lin_wei", "chr_gao_ren"], "goal": "Register the tally.", "conflict": "A formal challenge under covenant cannot be ignored.", "outcome": "The tally is logged but the moot is stayed until the challenge is answered.", "depends_on": ["scn_masters_tally"]},
                    ],
                },
                {
                    "id": "act_rising", "title": "Rising Action", "purpose": "rising_action",
                    "scenes": [
                        {"id": "scn_reed_crossing", "title": "The Reed Crossing", "summary": "Crossing the reed flats toward the moot ground, Lin Wei is intercepted by Eel School adepts and escapes them over the reeds without drawing a blade.", "location_id": "loc_mist_rookery", "character_ids": ["chr_lin_wei", "chr_gao_ren"], "goal": "Reach Saltmarket with the tally.", "conflict": "Drawing a blade outside a witnessed duel would void her cause.", "outcome": "She crosses without breaking the covenant; Gao Ren's ambush shames his own school.", "depends_on": ["scn_challenge_posted"]},
                        {"id": "scn_saltmarket_petition", "title": "The Warden's Book", "summary": "Lin Wei petitions Mei Sura to convene the moot under the market peace, and Mei stakes her office on the tally's validity.", "location_id": "loc_saltmarket_isle", "character_ids": ["chr_lin_wei", "chr_mei_sura"], "goal": "Win the moot ground.", "conflict": "Mei will not break neutrality for a disowned student.", "outcome": "The moot is convened on Saltmarket; the challenge must be answered there.", "depends_on": ["scn_reed_crossing"]},
                    ],
                },
                {
                    "id": "act_climax", "title": "Climax", "purpose": "climax",
                    "scenes": [
                        {"id": "scn_moot_duel", "title": "The Witnessed Duel", "summary": "Before the assembled envoys, Lin Wei answers Gao Ren's challenge in a formal duel at Bannerhall and wins on points, yielding the finishing stroke.", "location_id": "loc_bannerhall", "character_ids": ["chr_lin_wei", "chr_gao_ren", "chr_mei_sura"], "goal": "Answer the challenge and seat the moot.", "conflict": "Losing forfeits the tally; killing forfeits the peace.", "outcome": "The tally is upheld; Gao Ren yields and the moot is seated.", "depends_on": ["scn_saltmarket_petition"]},
                    ],
                },
                {
                    "id": "act_resolution", "title": "Resolution", "purpose": "resolution",
                    "scenes": [
                        {"id": "scn_rookery_truce", "title": "The Rookery Truce", "summary": "At the moot, the sects divide the eel grounds by season: the Eel School fishes after the cranes fledge, and the nesting ban stands.", "location_id": "loc_mist_rookery", "character_ids": ["chr_lin_wei", "chr_gao_ren", "chr_mei_sura"], "goal": "Settle the rookery rights.", "conflict": "Each sect must give up something to keep the covenant.", "outcome": "The truce is sworn under the Crane Banner; Lin Wei's name is restored.", "depends_on": ["scn_moot_duel"]},
                    ],
                },
            ],
        },
    },
    # ------------------------------------------------------------------
    # 3. Hard SF solar-sail shipyard
    # ------------------------------------------------------------------
    {
        "num": 3,
        "slug": "hard_sf_perihelion_yard",
        "gen_name": "v2_03_hard_sf_perihelion_yard",
        "evidence_summary": "The world, cast and storyboard satisfy the brief's orbital-mechanics shipyard setting; deterministic validators are clean and there are no blocking defects.",
        "brief": {
            "title": "Sunside",
            "premise": "A salvage rigger at a solar-sail shipyard inside Mercury's orbit finds a hull logged as scrapped still drawing power, and must prove it before the yard's charter auditors arrive.",
            "genre": "hard science fiction",
            "tone": "gritty",
            "target_audience": "adult",
            "location_count": 4,
            "constraints": [
                "forbid:teleporter",
                "require:sail",
                "No faster-than-light travel or communication; everything obeys orbital mechanics.",
                "max_locations:5",
            ],
        },
        "world": {
            "world_id": "wld_perihelion_yard",
            "name": "Perihelion Yard",
            "description": "A sail shipyard in a sun-grazing orbit inside Mercury's, where crews re-mirror sails under brutal heat budgets, and every gram of salvage is owed to the mass ledger.",
            "locations": [
                {"id": "loc_yard_spine", "name": "The Yard Spine", "description": "The kilometre-long gantry truss where sail hulls are berthed and re-mirrored."},
                {"id": "loc_mirror_shed", "name": "The Mirror Shed", "description": "A shadowed workshop where crews re-silver sail film under vacuum."},
                {"id": "loc_bastion_hulk", "name": "The Bastion Hulk", "description": "The radiation-shielded command module where the yard office and audit berth sit."},
                {"id": "loc_shadow_dock", "name": "Shadow Dock", "description": "A dry dock permanently eclipsed behind the yard's own truss, invisible to thermal survey."},
            ],
            "factions": [
                {"id": "fac_riggers_union", "name": "The Riggers' Union", "description": "The perihelion riggers' union, which holds the heat rosters and the safety charter.", "location_ids": ["loc_yard_spine", "loc_mirror_shed"]},
                {"id": "fac_charter_audit", "name": "The Charter Audit Office", "description": "Auditors with a permanent berth at the Bastion Hulk, empowered to seize the mass ledger.", "location_ids": ["loc_bastion_hulk"]},
                {"id": "fac_helio_tank", "name": "The Helio Tank Consortium", "description": "The owners' consortium that charters the yard and buys every scrapped hull.", "location_ids": ["loc_bastion_hulk"]},
            ],
            "rules": [
                {"id": "rul_light_delay", "statement": "A tight-beam reply from the inner system takes at least ten minutes; nobody gets an instant answer.", "category": "physics"},
                {"id": "rul_heat_budget", "statement": "No crew may work sunside longer than their logged heat budget allows; the duty log is law.", "category": "physics"},
                {"id": "rul_mass_ledger", "statement": "Every gram that leaves the yard is entered in the mass ledger; unlogged salvage is theft.", "category": "social"},
                {"id": "rul_shadow_dock", "statement": "Shadow Dock never sees the sun; anything berthed there does not register on thermal survey.", "category": "physics"},
            ],
            "history": [
                {"id": "evt_keel_year", "name": "The Keel Year", "era": "First Perihelion", "description": "The yard truss was assembled from cannibalised tankers to service the inner-system sail fleet.", "location_ids": ["loc_yard_spine"]},
                {"id": "evt_sail_fire", "name": "The Sail Fire", "era": "The Austerity", "description": "A mis-folded sail focused the sun onto a dock crew; the safety charter was rewritten in its wake.", "location_ids": ["loc_mirror_shed"]},
                {"id": "evt_audit_charter", "name": "The Audit Charter", "era": "The Austerity", "description": "The owners granted the audit office a permanent berth after a season of ledger fraud.", "location_ids": ["loc_bastion_hulk"]},
            ],
            "conflicts": [
                {"id": "cnf_scrap_ledger", "name": "The Scrap Ledger", "description": "The union suspects hulls logged as scrapped are being kept as spares in Shadow Dock, off the mass ledger.", "faction_ids": ["fac_riggers_union", "fac_charter_audit"]},
                {"id": "cnf_heat_roster", "name": "The Heat Roster", "description": "Helio Tank wants longer sunside shifts than the union's heat budget allows.", "faction_ids": ["fac_helio_tank", "fac_riggers_union"]},
            ],
        },
        "characters": {
            "world_id": "wld_perihelion_yard",
            "characters": [
                {
                    "id": "chr_ria_callum", "name": "Ria Callum", "role": "protagonist",
                    "description": "A salvage rigger with ten perihelion seasons on the Spine, who trusts torque wrenches and duty logs more than offices.",
                    "personality_traits": ["methodical", "suspicious", "loyal"],
                    "motivation": "To prove the scrapped hull is real before the auditors can bury it.",
                    "goal": "Document the ghost hull's power draw and get it on the record.",
                    "flaw": "She hoards evidence instead of trusting anyone with it.",
                    "internal_conflict": "She wants justice but fears what it will cost her crewmates' berths.",
                    "external_conflict": "The audit office can classify her evidence and her along with it.",
                    "home_location_id": "loc_yard_spine", "faction_id": "fac_riggers_union",
                    "abilities": [{"name": "Load-path reading", "description": "Traces power and load draws through a hull's conduit plan by inspection.", "category": "mental"}],
                    "arc": "Ria learns to put the evidence in other people's hands before it can be silenced.",
                },
                {
                    "id": "chr_director_savane", "name": "Director Savane", "role": "antagonist",
                    "description": "The audit director who certified the ghost hull's scrap certificate and controls what the charter sees.",
                    "personality_traits": ["impeccable", "patient", "controlling"],
                    "motivation": "To close the merger before the spare hull is discovered on the books.",
                    "goal": "Keep the Shadow Dock berth unlogged until the merger seals.",
                    "flaw": "He believes procedure shields him from arithmetic.",
                    "internal_conflict": "He knows the hull is irregular but has convinced himself it is necessary.",
                    "external_conflict": "Ria's measurements put the lie in his own ledger.",
                    "home_location_id": "loc_bastion_hulk", "faction_id": "fac_charter_audit",
                    "abilities": [{"name": "Ledger forensics", "description": "Finds and hides discrepancies inside mass ledgers better than anyone in the audit office.", "category": "mental"}],
                    "arc": "Savane's own charter turns on him when the numbers are read aloud.",
                },
                {
                    "id": "chr_bex_osei", "name": "Bex Osei", "role": "supporting",
                    "description": "The Mirror Shed forewoman who re-silvers sail film and guards her crew's heat budget like blood.",
                    "personality_traits": ["blunt", "protective", "unflappable"],
                    "motivation": "To keep her crew under budget and out of the audit's way.",
                    "goal": "Verify the mass-ledger gap without burning her crew's exposure.",
                    "flaw": "She shields her people so hard they never see the whole truth.",
                    "internal_conflict": "Helping Ria means endangering the crew she protects.",
                    "external_conflict": "The audit can pull her crew's heat budget if she cooperates.",
                    "home_location_id": "loc_mirror_shed", "faction_id": "fac_riggers_union",
                    "abilities": [{"name": "Film-welding", "description": "Splices and re-silvers torn sail film in vacuum under a strict time budget.", "category": "technological"}],
                    "arc": "Bex stops protecting her crew from the truth and lets them choose it.",
                },
            ],
            "relationships": [
                {"id": "rel_ria_bex", "source_character_id": "chr_ria_callum", "target_character_id": "chr_bex_osei", "relationship_type": "ally", "description": "Bex is the only forewoman Ria trusts with the ledger gap.", "conflict": "Bex wants it handled quietly; Ria wants it on the record."},
                {"id": "rel_ria_savane", "source_character_id": "chr_ria_callum", "target_character_id": "chr_director_savane", "relationship_type": "adversary", "description": "Savane audited the scrap certificate Ria is disproving.", "conflict": "Each controls a different copy of the truth."},
            ],
        },
        "storyboard": {
            "world_id": "wld_perihelion_yard",
            "title": "Sunside",
            "logline": "A salvage rigger proves a scrapped hull is alive in Shadow Dock before the charter auditors can make it, and her, disappear.",
            "theme": "the ledger remembers",
            "acts": [
                {
                    "id": "act_setup", "title": "Setup", "purpose": "setup",
                    "scenes": [
                        {"id": "scn_power_draw", "title": "The Unlogged Draw", "summary": "Stripping a berth on the Yard Spine, Ria finds a live power tap feeding a hull that the manifest says does not exist.", "location_id": "loc_yard_spine", "character_ids": ["chr_ria_callum"], "goal": "Confirm the anomalous draw.", "conflict": "Logging it honestly flags her own shift for audit.", "outcome": "Ria measures the draw and keeps the readings off the shared log.", "depends_on": []},
                        {"id": "scn_shadow_berth", "title": "The Ghost Berth", "summary": "Ria crosses to Shadow Dock and boards the hull: powered, warm and provisioned, certified scrapped a season ago.", "location_id": "loc_shadow_dock", "character_ids": ["chr_ria_callum"], "goal": "Verify the hull exists.", "conflict": "Entry to an unlogged berth breaches the duty log.", "outcome": "She photographs the hull's registry plate and its live feed.", "depends_on": ["scn_power_draw"]},
                    ],
                },
                {
                    "id": "act_rising", "title": "Rising Action", "purpose": "rising_action",
                    "scenes": [
                        {"id": "scn_ledger_gap", "title": "The Missing Mass", "summary": "In the Mirror Shed, Bex reconciles the film inventory and finds the same unlogged mass: somebody has been feeding a spare hull for a year.", "location_id": "loc_mirror_shed", "character_ids": ["chr_ria_callum", "chr_bex_osei"], "goal": "Confirm the ledger gap.", "conflict": "Confirming it means reporting it, which endangers the crew.", "outcome": "The gap is real; Bex agrees to help on condition the crew stays clear.", "depends_on": ["scn_shadow_berth"]},
                        {"id": "scn_auditor_lands", "title": "The Early Audit", "summary": "Director Savane lands at the Bastion Hulk a week early and begins sealing ledgers, cutting off Ria's window to file.", "location_id": "loc_bastion_hulk", "character_ids": ["chr_director_savane", "chr_ria_callum"], "goal": "Pre-empt the audit.", "conflict": "Savane controls which records the charter ever sees.", "outcome": "Ria's evidence is marked for seizure; she has one duty cycle left.", "depends_on": ["scn_ledger_gap"]},
                    ],
                },
                {
                    "id": "act_climax", "title": "Climax", "purpose": "climax",
                    "scenes": [
                        {"id": "scn_evidence_handover", "title": "The Handover", "summary": "At the Bastion Hulk, Ria presents the registry plate and the mass gap to the full audit board, trading immunity for her crew against Savane's classification order.", "location_id": "loc_bastion_hulk", "character_ids": ["chr_ria_callum", "chr_director_savane", "chr_bex_osei"], "goal": "Get the evidence on the record.", "conflict": "Savane offers to bury the case and the crew's amnesty together.", "outcome": "The board orders Shadow Dock opened; Savane's charter is revoked.", "depends_on": ["scn_auditor_lands"]},
                    ],
                },
                {
                    "id": "act_resolution", "title": "Resolution", "purpose": "resolution",
                    "scenes": [
                        {"id": "scn_charter_recount", "title": "The Recount", "summary": "The ledger is reopened on the Spine, the ghost hull is logged and sold to fund the union's safety charter, and the heat roster stands.", "location_id": "loc_yard_spine", "character_ids": ["chr_ria_callum", "chr_bex_osei"], "goal": "Restore the ledger.", "conflict": "The vindicated numbers still cost the yard its season.", "outcome": "The union signs the recount; the yard sails lighter and honest.", "depends_on": ["scn_evidence_handover"]},
                    ],
                },
            ],
        },
    },
    # ------------------------------------------------------------------
    # 4. Post-apocalyptic hopepunk seedways
    # ------------------------------------------------------------------
    {
        "num": 4,
        "slug": "postapocalyptic_seedways",
        "gen_name": "v2_04_postapocalyptic_seedways",
        "evidence_summary": "The world, cast and storyboard satisfy the brief's hand-tool seedway setting; deterministic validators are clean and there are no blocking defects.",
        "brief": {
            "title": "What the Rain Remembers",
            "premise": "A seed-keeper's caravan must cross three recovering valley towns before the last frost, trading grain stock and mending an old feud that split the seedway routes.",
            "genre": "post-apocalyptic",
            "tone": "wistful but hopeful",
            "target_audience": "adult",
            "location_count": 4,
            "constraints": [
                "forbid:spaceship",
                "require:seed",
                "Technology is pre-industrial salvaged hand-tools; nothing powered remains.",
                "max_locations:5",
            ],
        },
        "world": {
            "world_id": "wld_seedways",
            "name": "The Seedways",
            "description": "Generations after the Blight Year emptied the fields, valley towns survive on shared seed stock hauled by caravan along the seedway routes between the last granary and the first orchards.",
            "locations": [
                {"id": "loc_granary_hill", "name": "Granary Hill", "description": "Terraced seed-vaults cut into the hill, where the tithe grain is graded and sealed."},
                {"id": "loc_ford_market", "name": "Ford Market", "description": "The river-crossing market where the seedways meet and the weigh-house keeps the tithe ledgers."},
                {"id": "loc_ash_orchards", "name": "The Ash Orchards", "description": "Replanting rows on blight-ash soil, tended by families who took the worst land first."},
                {"id": "loc_frost_gate", "name": "The Frost Gate", "description": "The high pass that closes on the last frost and strands whatever is caught beyond it."},
            ],
            "factions": [
                {"id": "fac_seed_keepers", "name": "The Seed Keepers", "description": "A caravan order sworn to grade, seal and carry seed stock between the valleys.", "location_ids": ["loc_granary_hill"]},
                {"id": "fac_millers_compact", "name": "The Millers' Compact", "description": "The town millers who weigh tithe grain and hold the market charters.", "location_ids": ["loc_ford_market"]},
                {"id": "fac_orchard_families", "name": "The Orchard Families", "description": "The planters who took the blight-ash land and are owed grafting stock by the vaults.", "location_ids": ["loc_ash_orchards"]},
            ],
            "rules": [
                {"id": "rul_seed_tithe", "statement": "Every town that draws from the seed vaults returns two measures at harvest for each measure taken.", "category": "social"},
                {"id": "rul_no_engines", "statement": "No powered machinery survived the Blight; all work is done by hand, beast and water.", "category": "technology"},
                {"id": "rul_frost_gate", "statement": "The Frost Gate closes on the last frost; a caravan caught beyond it winters alone.", "category": "physics"},
                {"id": "rul_grain_truth", "statement": "A keeper who adulterates seed stock is struck from the rolls and their name is never carried by the caravans again.", "category": "social"},
            ],
            "history": [
                {"id": "evt_blight_year", "name": "The Blight Year", "era": "The Ruin", "description": "The blight emptied the fields; survivors sealed the first vaults on Granary Hill.", "location_ids": ["loc_granary_hill"]},
                {"id": "evt_first_seedway", "name": "The First Seedway", "era": "The Mending", "description": "The first caravan circuit joined the three valleys and made the tithe system possible.", "location_ids": ["loc_ford_market"]},
                {"id": "evt_millers_split", "name": "The Millers' Split", "era": "The Mending", "description": "A falsified tithe ledger at Ford Market split the routes for a generation.", "location_ids": ["loc_ford_market"]},
            ],
            "conflicts": [
                {"id": "cnf_forged_tithe", "name": "The Cut Grain", "description": "Someone is diluting tithe grain with chaff at the weigh-house, and the keepers and millers each blame the other.", "faction_ids": ["fac_millers_compact", "fac_seed_keepers"]},
                {"id": "cnf_orchard_claims", "name": "The Orchard Claims", "description": "The orchard families claim vault grain promised to them is being carried to the caravan instead.", "faction_ids": ["fac_orchard_families", "fac_seed_keepers"]},
            ],
        },
        "characters": {
            "world_id": "wld_seedways",
            "characters": [
                {
                    "id": "chr_tove_marka", "name": "Tove Marka", "role": "protagonist",
                    "description": "A seed-keeper of the vault caravan, raised on the routes, who grades grain by eye and counts winters like coin.",
                    "personality_traits": ["patient", "exact", "self-reliant"],
                    "motivation": "To see the seedways whole again before she hands on her satchel.",
                    "goal": "Reach Ford Market with sound stock before the last frost.",
                    "flaw": "She carries the whole route alone and will not be helped.",
                    "internal_conflict": "Mending the split means trusting the people who broke it.",
                    "external_conflict": "The cut tithe grain makes every town suspect her caravan.",
                    "home_location_id": "loc_granary_hill", "faction_id": "fac_seed_keepers",
                    "abilities": [{"name": "Seed-scoring", "description": "Judges germination and adulteration in a sack of grain by eye and weight.", "category": "mental"}],
                    "arc": "Tove learns that a route no one else can walk is a route that dies with her.",
                },
                {
                    "id": "chr_alder_vane", "name": "Alder Vane", "role": "antagonist",
                    "description": "The compact factor at Ford Market who diluted the tithe grain to keep his town's mill turning through a hard year.",
                    "personality_traits": ["urbane", "cornered", "pragmatic"],
                    "motivation": "To protect his town from an audit that would starve it.",
                    "goal": "Conceal the diluted tithe until after the thaw audit.",
                    "flaw": "He believes a debt concealed is a debt half-paid.",
                    "internal_conflict": "He knows the orchard families paid for his town's lie.",
                    "external_conflict": "Tove's inspection can read the chaff in his sacks.",
                    "home_location_id": "loc_ford_market", "faction_id": "fac_millers_compact",
                    "abilities": [{"name": "Weigh-house politics", "description": "Reads markets, credit and debtors well enough to move a ledger without leaving fingerprints.", "category": "social"}],
                    "arc": "Vane must confess the cut grain or watch the routes close around him.",
                },
                {
                    "id": "chr_nuna_brack", "name": "Nuna Brack", "role": "supporting",
                    "description": "An orchard daughter who grafts blight-hardy stock and carries her family's claim to the promised grain.",
                    "personality_traits": ["direct", "hopeful", "stubborn"],
                    "motivation": "To win the grafting stock her family's orchard was promised.",
                    "goal": "Make the caravan honour the orchard claims before the frost.",
                    "flaw": "She presses her claim so hard it sounds like a threat.",
                    "internal_conflict": "She distrusts every keeper yet needs this caravan.",
                    "external_conflict": "The caravan and the millers both call her claim premature.",
                    "home_location_id": "loc_ash_orchards", "faction_id": "fac_orchard_families",
                    "abilities": [{"name": "Graft-keeping", "description": "Keeps grafted stock alive through cold snaps and rough travel.", "category": "physical"}],
                    "arc": "Nuna wins her stock by helping the caravan prove the fraud that cheated it.",
                },
            ],
            "relationships": [
                {"id": "rel_tove_nuna", "source_character_id": "chr_tove_marka", "target_character_id": "chr_nuna_brack", "relationship_type": "ally", "description": "Nuna rides with the caravan to press the orchard claim.", "conflict": "Tove cannot honour the claim until the tithe fraud is proven."},
                {"id": "rel_tove_alder", "source_character_id": "chr_tove_marka", "target_character_id": "chr_alder_vane", "relationship_type": "adversary", "description": "Tove's seed-scoring can expose Vane's diluted tithe.", "conflict": "Vane must stall her inspection past the frost."},
            ],
        },
        "storyboard": {
            "world_id": "wld_seedways",
            "title": "What the Rain Remembers",
            "logline": "A seed-keeper carries sound stock and a buried fraud across three valleys before the frost, and mends the split that broke the seedways.",
            "theme": "trust measured in grain",
            "acts": [
                {
                    "id": "act_setup", "title": "Setup", "purpose": "setup",
                    "scenes": [
                        {"id": "scn_vault_audit", "title": "Chaff in the Sacks", "summary": "Sealing the tithe sacks at Granary Hill, Tove scores the grain and finds chaff cut into the Ford Market delivery.", "location_id": "loc_granary_hill", "character_ids": ["chr_tove_marka"], "goal": "Certify the tithe stock.", "conflict": "Reporting the cut grain accuses the market that feeds the routes.", "outcome": "Tove seals the evidence and carries it with the caravan.", "depends_on": []},
                        {"id": "scn_caravan_leaves", "title": "The Last Circuit", "summary": "The caravan departs for the last circuit before the Frost Gate closes, with Tove riding guard on the suspect sacks.", "location_id": "loc_frost_gate", "character_ids": ["chr_tove_marka"], "goal": "Reach Ford Market before the frost.", "conflict": "Every day lost to weather is a day the gate is nearer shut.", "outcome": "The caravan takes the long seedway through the orchards.", "depends_on": ["scn_vault_audit"]},
                    ],
                },
                {
                    "id": "act_rising", "title": "Rising Action", "purpose": "rising_action",
                    "scenes": [
                        {"id": "scn_orchard_stay", "title": "The Orchard Claim", "summary": "At the Ash Orchards, Nuna demands the promised grafting stock; Tove shows her the cut grain that is starving both claims.", "location_id": "loc_ash_orchards", "character_ids": ["chr_tove_marka", "chr_nuna_brack"], "goal": "Pass the orchards without forfeiting stock.", "conflict": "Nuna's claim is just, but the caravan's grain is already spoken for.", "outcome": "Nuna joins the caravan to see the fraud proven and her claim honoured.", "depends_on": ["scn_caravan_leaves"]},
                        {"id": "scn_weigh_house", "title": "The Weigh-House", "summary": "At Ford Market, Alder Vane stalls the audit with courtesy and credit, while Tove scores the market sacks and finds the same cut grain.", "location_id": "loc_ford_market", "character_ids": ["chr_tove_marka", "chr_alder_vane", "chr_nuna_brack"], "goal": "Prove the tithe was diluted at the market.", "conflict": "Vane's charter lets him delay any audit past the frost.", "outcome": "Tove finds the proof; Vane calls the caravan's own honesty into question.", "depends_on": ["scn_orchard_stay"]},
                    ],
                },
                {
                    "id": "act_climax", "title": "Climax", "purpose": "climax",
                    "scenes": [
                        {"id": "scn_frost_race", "title": "Before the Gate", "summary": "With the true ledger seized and the frost closing, Tove races Vane's hired riders to the Frost Gate to put the evidence beyond the market's reach.", "location_id": "loc_frost_gate", "character_ids": ["chr_tove_marka", "chr_alder_vane", "chr_nuna_brack"], "goal": "Carry the true ledger through the gate.", "conflict": "Vane needs the evidence lost before the thaw audit.", "outcome": "The caravan clears the gate at last light; the ledger is safe in the vault towns.", "depends_on": ["scn_weigh_house"]},
                    ],
                },
                {
                    "id": "act_resolution", "title": "Resolution", "purpose": "resolution",
                    "scenes": [
                        {"id": "scn_shared_granary", "title": "The Rejoined Routes", "summary": "At the thaw audit, the tithe is honestly weighed, the orchards receive their grafting stock, and the split routes are rejoined under one ledger.", "location_id": "loc_ford_market", "character_ids": ["chr_tove_marka", "chr_nuna_brack", "chr_alder_vane"], "goal": "Settle the tithe and the claims.", "conflict": "Confessing the fraud costs Vane's town its winter credit.", "outcome": "The routes are rejoined; the seedways run whole for the first time in a generation.", "depends_on": ["scn_frost_race"]},
                    ],
                },
            ],
        },
    },
    # ------------------------------------------------------------------
    # 5. Mythic fantasy underworld counting-house
    # ------------------------------------------------------------------
    {
        "num": 5,
        "slug": "mythic_underworld_ledger",
        "gen_name": "v2_05_mythic_underworld_ledger",
        "evidence_summary": "The world, cast and storyboard satisfy the brief's bureaucratic afterlife setting; deterministic validators are clean and there are no blocking defects.",
        "brief": {
            "title": "The Last Audit",
            "premise": "A junior scribe in the courts of the dead finds a mortal soul tallied to the wrong ledger column, and must carry the correction up through the counting-houses before the soul is weighed.",
            "genre": "mythic fantasy",
            "tone": "wry and solemn",
            "target_audience": "adult",
            "location_count": 5,
            "constraints": [
                "forbid:resurrection",
                "require:ledger",
                "The dead cannot return to life; only their accounts move.",
                "max_locations:6",
            ],
        },
        "world": {
            "world_id": "wld_underworld_ledger",
            "name": "The Underworld Ledger",
            "description": "The dead are governed as an endless counting-house: every mortal life is tallied in ledgers, and each arriving soul is weighed against its account before it is allowed to rest.",
            "locations": [
                {"id": "loc_gate_of_receipts", "name": "The Gate of Receipts", "description": "The arrival gate where each soul surrenders its tally-slip and is queued for weighing."},
                {"id": "loc_counting_halls", "name": "The Counting Halls", "description": "Warrens of desks where scribes transcribe mortal lives into the ledgers."},
                {"id": "loc_hall_of_scales", "name": "The Hall of Scales", "description": "The weighing chamber where souls are measured against their ledger entries."},
                {"id": "loc_erasure_wells", "name": "The Erasure Wells", "description": "Black shafts where accounts that cannot be balanced are dissolved."},
                {"id": "loc_lamp_archive", "name": "The Lamp Archive", "description": "Sealed stacks holding the ledgers of the long dead, tended by lamplight."},
            ],
            "factions": [
                {"id": "fac_scribes_order", "name": "The Order of Scribes", "description": "The clerks who transcribe mortal lives and vouch for every ledger entry.", "location_ids": ["loc_counting_halls"]},
                {"id": "fac_weighers", "name": "The Collegium of Weighers", "description": "The officers who weigh souls and certify the balances.", "location_ids": ["loc_hall_of_scales"]},
                {"id": "fac_lamplighters", "name": "The Lamplighter Kin", "description": "Keepers of the Lamp Archive and its sealed pages.", "location_ids": ["loc_lamp_archive"]},
            ],
            "rules": [
                {"id": "rul_no_return", "statement": "No soul returns to the living; the courts can only correct what is written.", "category": "metaphysics"},
                {"id": "rul_three_keys", "statement": "A ledger correction stands only if sealed by three keys: a scribe, a weigher and a lamplighter.", "category": "social"},
                {"id": "rul_erasure", "statement": "A soul weighed against a miscast ledger is sent to the Erasure Wells.", "category": "metaphysics"},
                {"id": "rul_lamp_oath", "statement": "A lamplighter who reads a sealed page aloud loses their lamp and their post.", "category": "social"},
            ],
            "history": [
                {"id": "evt_first_tally", "name": "The First Tally", "era": "The Founding Count", "description": "The first ledger was opened so the dead could be judged by what was written, not by what was remembered.", "location_ids": ["loc_counting_halls"]},
                {"id": "evt_wrong_war", "name": "The War of the Wrong Column", "era": "The Discordant Count", "description": "Rival weigher houses weighed the same souls twice over a column dispute, and the wells ran dark for a season.", "location_ids": ["loc_hall_of_scales", "loc_erasure_wells"]},
                {"id": "evt_lamp_seal", "name": "The Lamp Seal", "era": "The Concordant Count", "description": "The three-key rule was instituted so no correction could be sealed by one office alone.", "location_ids": ["loc_lamp_archive"]},
            ],
            "conflicts": [
                {"id": "cnf_miscast_ledger", "name": "The Miscast Harvest", "description": "Miscast tallies are rising this count, and the scribes and weighers each blame the other's desk.", "faction_ids": ["fac_scribes_order", "fac_weighers"]},
                {"id": "cnf_archive_access", "name": "The Sealed Ledgers", "description": "The lamplighters refuse to open sealed ledgers for the audit without a weigher's warrant.", "faction_ids": ["fac_lamplighters", "fac_weighers"]},
            ],
        },
        "characters": {
            "world_id": "wld_underworld_ledger",
            "characters": [
                {
                    "id": "chr_itho_pel", "name": "Itho Pel", "role": "protagonist",
                    "description": "A junior scribe of the Counting Halls who copies mortal accounts and notices errors his seniors prefer to overlook.",
                    "personality_traits": ["meticulous", "earnest", "obstinate"],
                    "motivation": "To see the soul weighed against what it actually did.",
                    "goal": "Get the miscast entry corrected and triple-sealed before the weighing.",
                    "flaw": "He trusts ink more than people, and says so.",
                    "internal_conflict": "Correcting the ledger means accusing the offices that feed him.",
                    "external_conflict": "The weighers' collegium bars a junior scribe from the scales.",
                    "home_location_id": "loc_counting_halls", "faction_id": "fac_scribes_order",
                    "abilities": [{"name": "Fault-sight", "description": "Spots a mis-tallied column at a glance, the way a proof-reader spots a dropped letter.", "category": "mental"}],
                    "arc": "Itho learns that a correction is only ink until three unwilling hands agree to seal it.",
                },
                {
                    "id": "chr_dame_ors", "name": "Dame Ors", "role": "antagonist",
                    "description": "A senior weigher of the collegium who certified the miscast harvest of tallies and guards the scales' reputation as her own.",
                    "personality_traits": ["august", "unyielding", "self-deceiving"],
                    "motivation": "To protect the weighers' infallibility, on which the whole court rests.",
                    "goal": "Quash the audit and weigh the soul as written.",
                    "flaw": "She calls her concealment mercy.",
                    "internal_conflict": "She knows the column is wrong and has convinced herself the error is small.",
                    "external_conflict": "Itho's correction would put her seal beside the error.",
                    "home_location_id": "loc_hall_of_scales", "faction_id": "fac_weighers",
                    "abilities": [{"name": "Scale-craft", "description": "Reads a soul's weight to the last dram and detects a doctored balance.", "category": "supernatural"}],
                    "arc": "Dame Ors must choose between the scales' honesty and her own.",
                },
                {
                    "id": "chr_hemo_lux", "name": "Hemo Lux", "role": "supporting",
                    "description": "A lamplighter archivist who tends the sealed stacks and remembers the index of every ledger he is forbidden to read.",
                    "personality_traits": ["wry", "careful", "melancholy"],
                    "motivation": "To keep the archive honest without breaking his lamp oath.",
                    "goal": "Produce the matching archive entry without reading a sealed page.",
                    "flaw": "He hides behind procedure when courage would serve better.",
                    "internal_conflict": "His oath protects the dead but shelters the fraud.",
                    "external_conflict": "Dame Ors threatens his lamp if he assists the audit.",
                    "home_location_id": "loc_lamp_archive", "faction_id": "fac_lamplighters",
                    "abilities": [{"name": "Index memory", "description": "Recalls the position and cross-references of any sealed ledger without opening it.", "category": "mental"}],
                    "arc": "Hemo risks his lamp to give the correction its third key.",
                },
            ],
            "relationships": [
                {"id": "rel_itho_hemo", "source_character_id": "chr_itho_pel", "target_character_id": "chr_hemo_lux", "relationship_type": "ally", "description": "Hemo's index can find the matching entry that proves the miscast.", "conflict": "Helping Itho puts Hemo's lamp in jeopardy."},
                {"id": "rel_itho_ors", "source_character_id": "chr_itho_pel", "target_character_id": "chr_dame_ors", "relationship_type": "adversary", "description": "Dame Ors certified the harvest of tallies Itho is auditing.", "conflict": "Her seal is required for the correction she wants buried."},
            ],
        },
        "storyboard": {
            "world_id": "wld_underworld_ledger",
            "title": "The Last Audit",
            "logline": "A junior scribe races a correction through three offices of the dead before a mis-tallied soul is weighed on a false account.",
            "theme": "what is written endures",
            "acts": [
                {
                    "id": "act_setup", "title": "Setup", "purpose": "setup",
                    "scenes": [
                        {"id": "scn_wrong_column", "title": "The Wrong Column", "summary": "Copying accounts in the Counting Halls, Itho finds a charitable soul tallied into the debtors' column.", "location_id": "loc_counting_halls", "character_ids": ["chr_itho_pel"], "goal": "Verify the miscast entry.", "conflict": "Flagging it accuses the weigher who certified it.", "outcome": "Itho files a correction notice and is warned to drop it.", "depends_on": []},
                        {"id": "scn_receipts_race", "title": "The Tally-Slip", "summary": "At the Gate of Receipts, the mis-tallied soul surrenders its slip and is queued for weighing; the queue is short.", "location_id": "loc_gate_of_receipts", "character_ids": ["chr_itho_pel"], "goal": "Learn when the soul will be weighed.", "conflict": "The weighing queue cannot be paused by a junior scribe.", "outcome": "The weighing is set for the third bell; Itho has that long.", "depends_on": ["scn_wrong_column"]},
                    ],
                },
                {
                    "id": "act_rising", "title": "Rising Action", "purpose": "rising_action",
                    "scenes": [
                        {"id": "scn_weigher_denial", "title": "The Weigher's Seal", "summary": "Itho petitions at the Hall of Scales; Dame Ors refuses the correction and revokes his petitioner's badge.", "location_id": "loc_hall_of_scales", "character_ids": ["chr_itho_pel", "chr_dame_ors"], "goal": "Win a weigher's key.", "conflict": "Dame Ors certified the harvest and will not audit herself.", "outcome": "Itho leaves without her seal, but with her ledger copy.", "depends_on": ["scn_receipts_race"]},
                        {"id": "scn_archive_index", "title": "The Lamp Index", "summary": "In the Lamp Archive, Hemo finds the matching entry's index cross-reference, which alone can prove the column switch.", "location_id": "loc_lamp_archive", "character_ids": ["chr_itho_pel", "chr_hemo_lux"], "goal": "Find proof in the archive.", "conflict": "The proof sits in a sealed ledger Hemo may not read.", "outcome": "The index itself proves the switch; Hemo offers his key.", "depends_on": ["scn_weigher_denial"]},
                    ],
                },
                {
                    "id": "act_climax", "title": "Climax", "purpose": "climax",
                    "scenes": [
                        {"id": "scn_three_keys", "title": "Three Keys", "summary": "At the weighing, Itho lays the index proof before the court; shamed by her own ledgers, Dame Ors sets her seal with the scribe and the lamplighter.", "location_id": "loc_hall_of_scales", "character_ids": ["chr_itho_pel", "chr_dame_ors", "chr_hemo_lux"], "goal": "Seal the correction before the weighing.", "conflict": "Ors must condemn herself to save the soul.", "outcome": "The correction is triple-sealed; the soul is weighed true.", "depends_on": ["scn_archive_index"]},
                    ],
                },
                {
                    "id": "act_resolution", "title": "Resolution", "purpose": "resolution",
                    "scenes": [
                        {"id": "scn_weighed_true", "title": "Weighed True", "summary": "The corrected account is read at the scales, the soul passes the wells unharmed, and the harvest audit is opened under three seals.", "location_id": "loc_hall_of_scales", "character_ids": ["chr_itho_pel", "chr_hemo_lux"], "goal": "Record the true weighing.", "conflict": "The audit Dame Ors feared now begins in earnest.", "outcome": "The ledgers are amended; the counting-houses learn to audit themselves.", "depends_on": ["scn_three_keys"]},
                    ],
                },
            ],
        },
    },
    # ------------------------------------------------------------------
    # 6. Gaslamp fantasy estuary city
    # ------------------------------------------------------------------
    {
        "num": 6,
        "slug": "gaslamp_bellwether",
        "gen_name": "v2_06_gaslamp_bellwether",
        "evidence_summary": "The world, cast and storyboard satisfy the brief's gas-lit storm-bell setting; deterministic validators are clean and there are no blocking defects.",
        "brief": {
            "title": "The Ninth Bell",
            "premise": "A bell-founder's apprentice in a fog-drowned estuary city hears the storm-bells ring a pattern no founder cast, and the parish orders the bells silenced before the next fog.",
            "genre": "gaslamp fantasy",
            "tone": "eerie",
            "target_audience": "adult",
            "location_count": 5,
            "constraints": [
                "forbid:electricity",
                "require:bell",
                "Lit by gas and oil only; no electrical devices.",
                "min_locations:4",
                "max_locations:6",
            ],
        },
        "world": {
            "world_id": "wld_bellwether",
            "name": "Bellwether",
            "description": "A gas-lit estuary city where nine bronze storm-bells on the sea-wall hold back the Chiming, a fog that steals the names of anyone it hears spoken.",
            "locations": [
                {"id": "loc_sea_wall", "name": "The Sea-Wall Belfry", "description": "The great wall mounting the nine storm-bells that ring the fog back."},
                {"id": "loc_founder_row", "name": "Founder Row", "description": "The foundry street where every bell was cast and struck with its maker's mark."},
                {"id": "loc_fogmarket", "name": "The Fogmarket", "description": "A licensed night market that opens only in fog, where names and secrets are traded."},
                {"id": "loc_bailiffs_stairs", "name": "Bailiff's Stairs", "description": "The steps up to the parish court where the watch's writs are read."},
                {"id": "loc_salt_chapel", "name": "The Salt Chapel", "description": "The chapel where every citizen's name is written on salt and kept against the fog."},
            ],
            "factions": [
                {"id": "fac_bell_founders", "name": "The Founder Collegium", "description": "The collegium of bell-founders who cast, tune and answer for every bell on the wall.", "location_ids": ["loc_founder_row"]},
                {"id": "fac_parish_watch", "name": "The Parish Watch", "description": "The wardens who keep the silence laws and can still a bell by writ.", "location_ids": ["loc_bailiffs_stairs"]},
                {"id": "fac_fog_brokers", "name": "The Fog Brokers", "description": "Licensed traders in names and secrets who work the Fogmarket under charter.", "location_ids": ["loc_fogmarket"]},
            ],
            "rules": [
                {"id": "rul_nine_bells", "statement": "The wall mounts nine bells and no more; casting a tenth is treason against the parish.", "category": "social"},
                {"id": "rul_fog_names", "statement": "In fog, a spoken name belongs to the fog; citizens carry name-tokens and answer to signs.", "category": "metaphysics"},
                {"id": "rul_founder_mark", "statement": "Every bell is struck with its founder's mark, and its ring can be traced back to the caster.", "category": "social"},
                {"id": "rul_salt_registry", "statement": "Every citizen's name is registered on salt at the chapel; an unregistered name is forfeit to the fog.", "category": "social"},
            ],
            "history": [
                {"id": "evt_wall_raised", "name": "The Raising of the Wall", "era": "The Ringing Years", "description": "Nine bells were cast and mounted on the sea-wall to hold the Chiming at bay.", "location_ids": ["loc_sea_wall"]},
                {"id": "evt_lost_parish", "name": "The Lost Parish", "era": "The Ringing Years", "description": "In a fog that lasted nine nights, a whole parish forgot its names; the salt registry was founded in answer.", "location_ids": ["loc_salt_chapel"]},
                {"id": "evt_brokers_charter", "name": "The Brokers' Charter", "era": "The Quiet Years", "description": "Trading in names was licensed and confined to the Fogmarket to keep it out of the parlours.", "location_ids": ["loc_fogmarket"]},
            ],
            "conflicts": [
                {"id": "cnf_tenth_ring", "name": "The Tenth Ring", "description": "An unmarked tenth bell has been heard in the pattern; the founders deny casting it and the watch wants the bells stilled.", "faction_ids": ["fac_bell_founders", "fac_parish_watch"]},
                {"id": "cnf_name_debts", "name": "The Name Debts", "description": "Fog brokers hold name-debts over half the parish; the watch calls it extortion, the brokers call it charter.", "faction_ids": ["fac_fog_brokers", "fac_parish_watch"]},
            ],
        },
        "characters": {
            "world_id": "wld_bellwether",
            "characters": [
                {
                    "id": "chr_elsa_quill", "name": "Elsa Quill", "role": "protagonist",
                    "description": "A bell-founder's apprentice on Founder Row who can read a casting flaw at a glance and hears the wall's bells like voices.",
                    "personality_traits": ["attentive", "earnest", "unbending"],
                    "motivation": "To prove the tenth ring was cast by a human hand and clear the collegium.",
                    "goal": "Trace the unmarked ring to its caster before the bells are stilled.",
                    "flaw": "She trusts craft rules too completely to see when they are being weaponised.",
                    "internal_conflict": "If the caster is not a founder, everything she was taught about marks is wrong.",
                    "external_conflict": "The parish watch has the writ to silence the wall and the will to use it.",
                    "home_location_id": "loc_founder_row", "faction_id": "fac_bell_founders",
                    "abilities": [{"name": "Ring-sight", "description": "Reads a bell's casting flaws and its founder's mark from its ring.", "category": "mental"}],
                    "arc": "Elsa learns that a mark is a signature, and signatures can be forged.",
                },
                {
                    "id": "chr_warden_hale", "name": "Warden Hale", "role": "antagonist",
                    "description": "The parish warden who signed the silence writ, whose own watch cast the unmarked bell to justify quietening the wall.",
                    "personality_traits": ["ordered", "zealous", "unrepentant"],
                    "motivation": "To still the bells, which he believes trade safety for superstition.",
                    "goal": "Silence the wall before the next fog, whatever it takes.",
                    "flaw": "He has made an end so just that no means can shame him.",
                    "internal_conflict": "He knows the fog is real but fears the bells' hold on the parish more.",
                    "external_conflict": "Elsa's ring-sight can prove the unmarked casting was the watch's work.",
                    "home_location_id": "loc_bailiffs_stairs", "faction_id": "fac_parish_watch",
                    "abilities": [{"name": "Writ authority", "description": "Moves writs through the parish court faster than anyone can answer them.", "category": "social"}],
                    "arc": "Hale's own unmarked bell tolls his confession.",
                },
                {
                    "id": "chr_tallow", "name": "Tallow", "role": "supporting",
                    "description": "A fog broker who trades in names from a licensed stall and knows which name the tenth bell was cast for.",
                    "personality_traits": ["sly", "honourable in trade", "nervous"],
                    "motivation": "To sell what he knows before the fog calls in his own name-debt.",
                    "goal": "Trade the ringer's true name for his own safe passage.",
                    "flaw": "He prices everything, including honesty.",
                    "internal_conflict": "Selling the name betrays the only client who ever paid fair.",
                    "external_conflict": "Both the watch and the founders would take the name without paying.",
                    "home_location_id": "loc_fogmarket", "faction_id": "fac_fog_brokers",
                    "abilities": [{"name": "Name-keeping", "description": "Keeps a bought name safe in memory through any fog.", "category": "other"}],
                    "arc": "Tallow sells the truth cheap, for once, and buys back his name.",
                },
            ],
            "relationships": [
                {"id": "rel_elsa_tallow", "source_character_id": "chr_elsa_quill", "target_character_id": "chr_tallow", "relationship_type": "ally", "description": "Tallow sells Elsa the clue to the unmarked bell's caster.", "conflict": "His price is a name-token she is sworn to protect."},
                {"id": "rel_elsa_hale", "source_character_id": "chr_elsa_quill", "target_character_id": "chr_warden_hale", "relationship_type": "adversary", "description": "Hale's silence writ is aimed at the wall Elsa maintains.", "conflict": "He rings the very treason he accuses the founders of."},
            ],
        },
        "storyboard": {
            "world_id": "wld_bellwether",
            "title": "The Ninth Bell",
            "logline": "A founder's apprentice proves the parish watch cast the unmarked bell it cites to silence the wall.",
            "theme": "who rings the alarm",
            "acts": [
                {
                    "id": "act_setup", "title": "Setup", "purpose": "setup",
                    "scenes": [
                        {"id": "scn_tenth_pattern", "title": "The Unmarked Ring", "summary": "On the Sea-Wall Belfry, Elsa hears a tenth ring in the pattern and reads no founder's mark in it.", "location_id": "loc_sea_wall", "character_ids": ["chr_elsa_quill"], "goal": "Identify the tenth ring.", "conflict": "An unmarked bell is either treason or forgery.", "outcome": "Elsa certifies the ring is bronze, cast by a skilled hand off the Row.", "depends_on": []},
                        {"id": "scn_silence_order", "title": "The Silence Writ", "summary": "At Bailiff's Stairs, Warden Hale reads a writ stilling the bells, citing the unmarked ring as proof the founders broke charter.", "location_id": "loc_bailiffs_stairs", "character_ids": ["chr_elsa_quill", "chr_warden_hale"], "goal": "Oppose the writ.", "conflict": "The writ is lawful unless the ring can be traced.", "outcome": "Elsa wins three days to trace the caster before the bells are stilled.", "depends_on": ["scn_tenth_pattern"]},
                    ],
                },
                {
                    "id": "act_rising", "title": "Rising Action", "purpose": "rising_action",
                    "scenes": [
                        {"id": "scn_fogmarket_price", "title": "The Broker's Price", "summary": "In the Fogmarket, Tallow sells Elsa a casting-mark rubbing found in the fog, priced in name-tokens.", "location_id": "loc_fogmarket", "character_ids": ["chr_elsa_quill", "chr_tallow"], "goal": "Buy the clue to the caster.", "conflict": "The price is a name she is sworn to protect.", "outcome": "She pays her own token; the rubbing bears the watch's foundry stamp.", "depends_on": ["scn_silence_order"]},
                        {"id": "scn_chapel_registry", "title": "The Salt Register", "summary": "At the Salt Chapel, the registry shows the ringer's name was never salted: someone the fog could not report.", "location_id": "loc_salt_chapel", "character_ids": ["chr_elsa_quill", "chr_tallow"], "goal": "Name the unregistered caster.", "conflict": "An unsalted name is proof and sacrilege at once.", "outcome": "The gap in the registry matches the watch's own bell-keeper.", "depends_on": ["scn_fogmarket_price"]},
                    ],
                },
                {
                    "id": "act_climax", "title": "Climax", "purpose": "climax",
                    "scenes": [
                        {"id": "scn_watch_ringer", "title": "The Watch's Bell", "summary": "On the wall, Elsa strikes the impounded tenth bell and reads its flaws aloud: it was cast in the watch's own foundry to fake a founder's treason.", "location_id": "loc_sea_wall", "character_ids": ["chr_elsa_quill", "chr_warden_hale", "chr_tallow"], "goal": "Prove the forgery before the court.", "conflict": "Hale's writ stands unless the proof rings true.", "outcome": "The mark is read; Hale's writ is void and his bell is condemned.", "depends_on": ["scn_chapel_registry"]},
                    ],
                },
                {
                    "id": "act_resolution", "title": "Resolution", "purpose": "resolution",
                    "scenes": [
                        {"id": "scn_bell_answered", "title": "The Answered Chiming", "summary": "The false bell is melted, the nine ring the next fog back over the wall, and Elsa's own mark is struck on the recast bronze.", "location_id": "loc_sea_wall", "character_ids": ["chr_elsa_quill", "chr_tallow"], "goal": "Restore the wall's trust.", "conflict": "The parish must trust the bells again after learning they can be forged.", "outcome": "The Chiming is answered; Bellwether keeps its names.", "depends_on": ["scn_watch_ringer"]},
                    ],
                },
            ],
        },
    },
    # ------------------------------------------------------------------
    # 7. Cozy fantasy travelling fair
    # ------------------------------------------------------------------
    {
        "num": 7,
        "slug": "cozy_thistledown_fair",
        "gen_name": "v2_07_cozy_thistledown_fair",
        "evidence_summary": "The world, cast and storyboard satisfy the brief's gentle travelling-fair setting; deterministic validators are clean and there are no blocking defects.",
        "brief": {
            "title": "Tea at the Ninth Stall",
            "premise": "A hedge-witch tea merchant follows a travelling fair that appears only in leap-season, trying to win back her family's lost stall before the fair folds its lanes and moves on.",
            "genre": "cozy fantasy",
            "tone": "gentle",
            "target_audience": "all ages",
            "location_count": 4,
            "constraints": [
                "forbid:violence",
                "require:fair",
                "Conflicts are settled by bargains, contests and trade, never violence.",
                "max_locations:5",
            ],
        },
        "world": {
            "world_id": "wld_thistledown",
            "name": "The Thistledown Fair",
            "description": "A travelling fair that unfolds its lanes only in leap-season, where stall rights are held in favours, debts are settled in trade, and the fair itself seems to remember every promise made under its lanterns.",
            "locations": [
                {"id": "loc_leap_lane", "name": "Leap Lane", "description": "The fair's main way, which appears in an ordinary field at leap-season and folds away at season's end."},
                {"id": "loc_ninth_stall", "name": "The Ninth Stall", "description": "A shuttered stall at the lane's turn whose lease was forfeited on an unkept favour a generation ago."},
                {"id": "loc_kettle_commons", "name": "The Kettle Commons", "description": "The cluster of tea tents where merchants trade gossip, samples and favours."},
                {"id": "loc_wishing_barn", "name": "The Wishing Barn", "description": "The tallykeepers' barn where every promised favour is written on a wishing tag and hung until kept."},
            ],
            "factions": [
                {"id": "fac_stallholders", "name": "The Stallholders' Round", "description": "The merchants who hold the fair's leases and vote the stall rights.", "location_ids": ["loc_kettle_commons"]},
                {"id": "fac_tallykeepers", "name": "The Tallykeepers", "description": "The clerks who record every favour on wishing tags and judge disputes of debt.", "location_ids": ["loc_wishing_barn"]},
                {"id": "fac_carters", "name": "The Carter Kin", "description": "The families whose wains carry the fair between fields and keep the lanes' secrets.", "location_ids": ["loc_leap_lane"]},
            ],
            "rules": [
                {"id": "rul_leap_season", "statement": "The fair exists only in leap-season; at season's end the lanes fold back into ordinary fields.", "category": "metaphysics"},
                {"id": "rul_favour_currency", "statement": "Debts at the fair are paid in favours, and a favour once promised must be kept before the fair moves.", "category": "social"},
                {"id": "rul_no_sharp_edges", "statement": "No contest at the fair may risk harm; disputes go to the Tallykeepers and are settled by bargain or contest.", "category": "social"},
                {"id": "rul_ninth_lease", "statement": "The Ninth Stall's lease can be claimed only by the family that lost it, before the third bell of closing day.", "category": "social"},
            ],
            "history": [
                {"id": "evt_first_fair", "name": "The First Fair", "era": "The First Leap", "description": "The fair appeared uninvited in a fallow field, traded for a season, and left a lane where none had been.", "location_ids": ["loc_leap_lane"]},
                {"id": "evt_stall_forfeit", "name": "The Forfeit of the Ninth", "era": "The Middle Leaps", "description": "A tea merchant's family lost their stall when a promised favour went unkept past the third bell.", "location_ids": ["loc_ninth_stall"]},
                {"id": "evt_tally_accord", "name": "The Tally Accord", "era": "The Middle Leaps", "description": "The tallykeepers were given authority over favour-debts after a season of duelling claims.", "location_ids": ["loc_wishing_barn"]},
            ],
            "conflicts": [
                {"id": "cnf_ninth_claim", "name": "The Ninth Claim", "description": "The Carter Kin are quietly selling the Ninth Stall's lease, while the family that forfeited it still holds a claim.", "faction_ids": ["fac_stallholders", "fac_carters"]},
                {"id": "cnf_favour_shortage", "name": "The Favour Shortage", "description": "More favours are owed than can be kept before closing day, and the tallykeepers must rule which debts ride with the fair.", "faction_ids": ["fac_tallykeepers", "fac_stallholders"]},
            ],
        },
        "characters": {
            "world_id": "wld_thistledown",
            "characters": [
                {
                    "id": "chr_poppy_wren", "name": "Poppy Wren", "role": "protagonist",
                    "description": "A hedge-witch tea merchant who brews her family's recipes from a handcart, carrying the deed-story of the Ninth Stall her grandmother lost.",
                    "personality_traits": ["warm", "persistent", "self-doubting"],
                    "motivation": "To win back the stall that is the last of her family's name at the fair.",
                    "goal": "Prove her family's claim to the Ninth Stall before the third bell of closing day.",
                    "flaw": "She apologises before she speaks, and hears refusal before it comes.",
                    "internal_conflict": "She wants the stall but fears the fair will find her unworthy of it.",
                    "external_conflict": "The Carter Kin's sale of the lease is lawful unless her claim is proven first.",
                    "home_location_id": "loc_kettle_commons", "faction_id": "fac_stallholders",
                    "abilities": [{"name": "Taste-truthing", "description": "Tastes sincerity in a shared cup of tea, a small hedge-witch gift.", "category": "supernatural"}],
                    "arc": "Poppy stops apologising for her claim and lets the fair judge it honestly.",
                },
                {
                    "id": "chr_damson_grey", "name": "Damson Grey", "role": "antagonist",
                    "description": "A carter-kin factor who found the Ninth Stall's lease bundled in an old ledger and means to sell it before the lanes fold.",
                    "personality_traits": ["charming", "literal-minded", "hungry"],
                    "motivation": "To turn a forgotten lease into the factor's share his kin never gave him.",
                    "goal": "Complete the lease sale before the family's claim can be proved.",
                    "flaw": "He believes the rules serve whoever reads them closest.",
                    "internal_conflict": "He knows the claim is real and tells himself a sale is a kind of settling.",
                    "external_conflict": "Poppy's claim and the tallykeepers' tags stand between him and the sale.",
                    "home_location_id": "loc_leap_lane", "faction_id": "fac_carters",
                    "abilities": [{"name": "Lease-craft", "description": "Finds the clause that lets him do what fairness forbids.", "category": "social"}],
                    "arc": "Damson reads one clause too many and finds the lease reads him back.",
                },
                {
                    "id": "chr_mabel_thorn", "name": "Mabel Thorn", "role": "supporting",
                    "description": "The eldest tallykeeper, who keeps the wishing tags and remembers the taste of every tea that ever sealed a bargain.",
                    "personality_traits": ["patient", "sly", "kind"],
                    "motivation": "To see debts kept and the fair's memory honoured.",
                    "goal": "Rule on the Ninth Stall claim by the tags alone.",
                    "flaw": "She lets the rules do the kindness she could do herself.",
                    "internal_conflict": "She found the forfeited favour long ago and kept it quietly on record.",
                    "external_conflict": "The carters resent any tallykeeper reading old tags aloud.",
                    "home_location_id": "loc_wishing_barn", "faction_id": "fac_tallykeepers",
                    "abilities": [{"name": "Tally memory", "description": "Recalls every wishing tag she ever hung, and who promised what.", "category": "mental"}],
                    "arc": "Mabel finally speaks the old tag aloud and lets the fair remember with her.",
                },
            ],
            "relationships": [
                {"id": "rel_poppy_mabel", "source_character_id": "chr_poppy_wren", "target_character_id": "chr_mabel_thorn", "relationship_type": "mentor", "description": "Mabel teaches Poppy how the fair's memory can carry her claim.", "conflict": "Mabel will not rule early; Poppy wants certainty now."},
                {"id": "rel_poppy_damson", "source_character_id": "chr_poppy_wren", "target_character_id": "chr_damson_grey", "relationship_type": "rival", "description": "Poppy's claim contests Damson's lease sale.", "conflict": "Only one of them can hold the stall at closing day."},
            ],
        },
        "storyboard": {
            "world_id": "wld_thistledown",
            "title": "Tea at the Ninth Stall",
            "logline": "A tea merchant proves her family's claim to a shuttered stall before the travelling fair folds its lanes for another year.",
            "theme": "kept promises",
            "acts": [
                {
                    "id": "act_setup", "title": "Setup", "purpose": "setup",
                    "scenes": [
                        {"id": "scn_fair_appears", "title": "The Lanes Unfold", "summary": "Poppy wheels her cart up Leap Lane as the fair unfolds, and finds the Ninth Stall shuttered under a For Sale tag.", "location_id": "loc_leap_lane", "character_ids": ["chr_poppy_wren"], "goal": "Learn why the stall is being sold.", "conflict": "Her family's claim must be proved before the sale completes.", "outcome": "Poppy registers a claim with the tallykeepers.", "depends_on": []},
                        {"id": "scn_lease_rumour", "title": "The Factor's Ledger", "summary": "At the Ninth Stall, Damson Grey shows the lease bundled in a carter ledger and gives her until closing day to contest it.", "location_id": "loc_ninth_stall", "character_ids": ["chr_poppy_wren", "chr_damson_grey"], "goal": "Read the lease terms.", "conflict": "The sale is lawful unless her family's claim is proven.", "outcome": "Poppy learns the forfeiture was an unkept favour, not a lost deed.", "depends_on": ["scn_fair_appears"]},
                    ],
                },
                {
                    "id": "act_rising", "title": "Rising Action", "purpose": "rising_action",
                    "scenes": [
                        {"id": "scn_favour_tally", "title": "The Wishing Tags", "summary": "In the Wishing Barn, Mabel Thorn traces the forfeited favour on its original tag: it was promised, and kept, a generation late.", "location_id": "loc_wishing_barn", "character_ids": ["chr_poppy_wren", "chr_mabel_thorn"], "goal": "Find the forfeited favour's record.", "conflict": "The tags rule claims, and this tag has a complication Mabel alone remembers.", "outcome": "The tag shows the favour was kept by Poppy's grandmother, too late to save the lease but true.", "depends_on": ["scn_lease_rumour"]},
                        {"id": "scn_kettle_contest", "title": "The Brewer's Contest", "summary": "At the Kettle Commons, Poppy stakes her claim on the fair's oldest contest: the family brew, tasted by the stallholders' round.", "location_id": "loc_kettle_commons", "character_ids": ["chr_poppy_wren", "chr_mabel_thorn", "chr_damson_grey"], "goal": "Prove the family craft the claim rests on.", "conflict": "A lost contest forfeits the claim's standing.", "outcome": "Her grandmother's recipe wins the round's vote and the right to be heard.", "depends_on": ["scn_favour_tally"]},
                    ],
                },
                {
                    "id": "act_climax", "title": "Climax", "purpose": "climax",
                    "scenes": [
                        {"id": "scn_third_bell", "title": "Before the Third Bell", "summary": "At the Ninth Stall as the third bell nears, Mabel reads the old tag aloud and rules the kept favour restores the family's claim.", "location_id": "loc_ninth_stall", "character_ids": ["chr_poppy_wren", "chr_damson_grey", "chr_mabel_thorn"], "goal": "Win the ruling before the bell.", "conflict": "Damson's sale closes at the third bell, whichever comes first.", "outcome": "The claim is upheld; the lease is Poppy's and Damson's ledger is impounded.", "depends_on": ["scn_kettle_contest"]},
                    ],
                },
                {
                    "id": "act_resolution", "title": "Resolution", "purpose": "resolution",
                    "scenes": [
                        {"id": "scn_stall_reclaimed", "title": "Tea at the Ninth Stall", "summary": "On closing day, Poppy opens the Ninth Stall, pays Damson's owed share fairly, and the fair folds its lanes with her family's name on the lease.", "location_id": "loc_kettle_commons", "character_ids": ["chr_poppy_wren", "chr_mabel_thorn", "chr_damson_grey"], "goal": "Settle every owed favour.", "conflict": "Victory that leaves a debt unpaid is only half a claim.", "outcome": "The stall reopens; every favour on the tags is kept.", "depends_on": ["scn_third_bell"]},
                    ],
                },
            ],
        },
    },
    # ------------------------------------------------------------------
    # 8. Space opera comet market
    # ------------------------------------------------------------------
    {
        "num": 8,
        "slug": "space_opera_comet_market",
        "gen_name": "v2_08_space_opera_comet_market",
        "evidence_summary": "The world, cast and storyboard satisfy the brief's nomad comet-market setting; deterministic validators are clean and there are no blocking defects.",
        "brief": {
            "title": "Ice and Coin",
            "premise": "A guild factotum on a nomad market built into a captured comet must arbitrate the theft of a sealed star-map before the comet's perihelion burn scatters the fleet.",
            "genre": "space opera",
            "tone": "swashbuckling",
            "target_audience": "adult",
            "location_count": 5,
            "constraints": [
                "forbid:laser",
                "require:comet",
                "Ships manoeuvre on sails, tethers and reaction plumes; no energy weapons.",
                "max_locations:6",
            ],
        },
        "world": {
            "world_id": "wld_comet_market",
            "name": "The Comet Market",
            "description": "A captured comet hollowed into a rotating bazaar that rides its own orbit, where guilds, pilots and ice-miners trade under burn articles until perihelion scatters them.",
            "locations": [
                {"id": "loc_core_vaults", "name": "The Core Vaults", "description": "Hollowed ice halls near the comet's heart where the ice barons keep their claims."},
                {"id": "loc_tether_docks", "name": "The Tether Docks", "description": "The sprawl of tethers where ships berth against the comet's slow spin."},
                {"id": "loc_map_house", "name": "The Map House", "description": "The guild house where star-maps are drawn, sealed and registered."},
                {"id": "loc_cinder_gardens", "name": "The Cinder Gardens", "description": "Sunward glasshouses in the slag skin where growers farm the perihelion light."},
                {"id": "loc_long_hall", "name": "The Long Hall", "description": "The arbitration hall where claims are heard under the burn articles."},
            ],
            "factions": [
                {"id": "fac_mapmakers", "name": "The Mapmakers' Guild", "description": "The guild that draws, seals and arbitrates every registered star-map.", "location_ids": ["loc_map_house", "loc_long_hall"]},
                {"id": "fac_ice_barons", "name": "The Ice Barons", "description": "Claim-holders who mine the core and buy up tethers before each burn.", "location_ids": ["loc_core_vaults"]},
                {"id": "fac_free_pilots", "name": "The Free Pilots' Compact", "description": "Independent pilots who fly the routes the guilds only chart.", "location_ids": ["loc_tether_docks"]},
            ],
            "rules": [
                {"id": "rul_burn_articles", "statement": "At perihelion every claim is settled or forfeited; nothing litigates through the burn.", "category": "social"},
                {"id": "rul_map_seal", "statement": "A sealed star-map may be opened only by its sealer or by the arbiter of the Long Hall.", "category": "social"},
                {"id": "rul_no_energy_arms", "statement": "Weapons aboard are blades, tools and harpoons; powered arms breach the market's charter.", "category": "technology"},
                {"id": "rul_ice_tithe", "statement": "Every ship pays an ice-tithe for its berth; unpaid tithes cost tether rights.", "category": "social"},
            ],
            "history": [
                {"id": "evt_capture", "name": "The Capture", "era": "The First Orbit", "description": "Free pilots netted the comet, hollowed its core and founded a market no planet could tax.", "location_ids": ["loc_core_vaults"]},
                {"id": "evt_map_wars", "name": "The Map Wars", "era": "The Second Orbit", "description": "Rival charts nearly wrecked the fleet at a perihelion; the guild won the right to seal every route.", "location_ids": ["loc_map_house"]},
                {"id": "evt_compact", "name": "The Pilots' Compact", "era": "The Third Orbit", "description": "The free pilots won arbitration rights in the Long Hall after refusing to fly sealed routes.", "location_ids": ["loc_long_hall", "loc_tether_docks"]},
            ],
            "conflicts": [
                {"id": "cnf_stolen_chart", "name": "The Stolen Chart", "description": "A sealed map of the perihelion route was stolen and resold; the guild calls it piracy, the pilot who holds it calls it salvage.", "faction_ids": ["fac_mapmakers", "fac_free_pilots"]},
                {"id": "cnf_tether_rights", "name": "The Tether Grab", "description": "The ice barons are buying up tethers before the burn, stranding pilots who owe ice-tithes.", "faction_ids": ["fac_ice_barons", "fac_free_pilots"]},
            ],
        },
        "characters": {
            "world_id": "wld_comet_market",
            "characters": [
                {
                    "id": "chr_sable_onuoha", "name": "Sable Onuoha", "role": "protagonist",
                    "description": "A factotum of the Mapmakers' Guild apprenticed to the Long Hall's arbiter, who reads broken seals the way pilots read weather.",
                    "personality_traits": ["precise", "fair-minded", "untested"],
                    "motivation": "To see the map settled by charter and not by whoever holds it last.",
                    "goal": "Arbitrate the stolen chart before the perihelion burn forfeits every claim.",
                    "flaw": "She believes procedure protects her from choosing sides.",
                    "internal_conflict": "The charter she serves may be wrong about who the map belongs to.",
                    "external_conflict": "Every claimant wants the arbitration to outlast the burn.",
                    "home_location_id": "loc_long_hall", "faction_id": "fac_mapmakers",
                    "abilities": [{"name": "Seal-reading", "description": "Reads a broken guild seal to tell when and by whom it was opened.", "category": "mental"}],
                    "arc": "Sable learns to judge the charter by what it costs, not what it says.",
                },
                {
                    "id": "chr_rho_vass", "name": "Rho Vass", "role": "antagonist",
                    "description": "A free pilot of the compact who bought the stolen map believing it was salvage and now holds the only copy of the burn route.",
                    "personality_traits": ["bold", "grievance-rich", "resourceful"],
                    "motivation": "To keep the route for the compact, which the guilds priced out of its own skies.",
                    "goal": "Hold the map until arbitration concedes the compact's claim.",
                    "flaw": "He cannot admit the fence was wrong because the cause feels right.",
                    "internal_conflict": "He stole nothing, yet everything he built rests on a theft.",
                    "external_conflict": "Sable's seal-reading can prove the map was opened before he bought it.",
                    "home_location_id": "loc_tether_docks", "faction_id": "fac_free_pilots",
                    "abilities": [{"name": "Perihelion piloting", "description": "Flies a sail rig through a burn approach better than any guild pilot.", "category": "physical"}],
                    "arc": "Rho trades the stolen map for a route the compact can win honestly.",
                },
                {
                    "id": "chr_kest_inger", "name": "Kest Inger", "role": "supporting",
                    "description": "An ice baron factor who bought the stolen map to convert it into tether rights and quietly started the Tether Grab.",
                    "personality_traits": ["suave", "acquisitive", "pragmatic"],
                    "motivation": "To turn the map into tethers before the burn makes every claim void.",
                    "goal": "Convert the chart into berth options he can sell at perihelion prices.",
                    "flaw": "He treats every debt as an asset until it is collected from him.",
                    "internal_conflict": "His father's ship was wrecked in the Map Wars; he swore never to starve on principle.",
                    "external_conflict": "If the theft is arbitrated, his purchases unwind with the claim.",
                    "home_location_id": "loc_core_vaults", "faction_id": "fac_ice_barons",
                    "abilities": [{"name": "Claim-stacking", "description": "Bundles claims, tithes and options so debtors owe him before they know it.", "category": "social"}],
                    "arc": "Kest's stacked claims collapse at perihelion and he must pick which debts to keep.",
                },
            ],
            "relationships": [
                {"id": "rel_sable_rho", "source_character_id": "chr_sable_onuoha", "target_character_id": "chr_rho_vass", "relationship_type": "opposed claimant", "description": "Sable arbitrates Rho's salvage claim on the stolen map.", "conflict": "Her charter calls it piracy; his compact calls it salvage."},
                {"id": "rel_sable_kest", "source_character_id": "chr_sable_onuoha", "target_character_id": "chr_kest_inger", "relationship_type": "counterparty", "description": "Kest's purchases unwind if Sable rules the map stolen.", "conflict": "He buys influence over the arbitration she must keep honest."},
            ],
        },
        "storyboard": {
            "world_id": "wld_comet_market",
            "title": "Ice and Coin",
            "logline": "A guild factotum arbitrates a stolen star-map as the comet's burn deadline makes every claimant desperate.",
            "theme": "whose route, whose rules",
            "acts": [
                {
                    "id": "act_setup", "title": "Setup", "purpose": "setup",
                    "scenes": [
                        {"id": "scn_seal_broken", "title": "The Broken Seal", "summary": "At the Map House, Sable inspects the recovered map and reads its seal: it was opened a week before Rho bought it.", "location_id": "loc_map_house", "character_ids": ["chr_sable_onuoha"], "goal": "Date the seal's breaking.", "conflict": "The date proves the map was fenced before it was salvaged.", "outcome": "Sable certifies the seal broken; arbitration is convened in the Long Hall.", "depends_on": []},
                        {"id": "scn_tether_panic", "title": "The Tether Grab", "summary": "At the Tether Docks, pilots find their berths sold out from under them as Kest's factors buy every option before the burn.", "location_id": "loc_tether_docks", "character_ids": ["chr_sable_onuoha", "chr_rho_vass", "chr_kest_inger"], "goal": "Gauge the stakes of the arbitration.", "conflict": "Whoever holds the route holds every tether.", "outcome": "The compact calls the grab a siege; the burn is a week out.", "depends_on": ["scn_seal_broken"]},
                    ],
                },
                {
                    "id": "act_rising", "title": "Rising Action", "purpose": "rising_action",
                    "scenes": [
                        {"id": "scn_long_hall_plea", "title": "The Salvage Plea", "summary": "In the Long Hall, Rho pleads salvage rights on the map; Sable's seal-reading shows the theft predates his purchase.", "location_id": "loc_long_hall", "character_ids": ["chr_sable_onuoha", "chr_rho_vass"], "goal": "Test the salvage claim.", "conflict": "A ruling of theft voids Rho's route and Kest's purchases alike.", "outcome": "Arbitration is stayed while Sable traces the thief.", "depends_on": ["scn_tether_panic"]},
                        {"id": "scn_cinder_lead", "title": "The Grower's Witness", "summary": "In the Cinder Gardens, a grower who saw the map change hands names Kest's factor as the fence's first buyer.", "location_id": "loc_cinder_gardens", "character_ids": ["chr_sable_onuoha", "chr_kest_inger"], "goal": "Identify the true thief's buyer.", "conflict": "The witness's testimony unwinds Kest's claim-stacks.", "outcome": "The chain leads to Kest's office; Sable summons him to the hall.", "depends_on": ["scn_long_hall_plea"]},
                    ],
                },
                {
                    "id": "act_climax", "title": "Climax", "purpose": "climax",
                    "scenes": [
                        {"id": "scn_burn_arbitration", "title": "The Burn Arbitration", "summary": "As perihelion nears, Sable rules in the Long Hall: the map is stolen, the route belongs to the fleet, and Kest's stacked claims are void; Rho trades his copy for first berth.", "location_id": "loc_long_hall", "character_ids": ["chr_sable_onuoha", "chr_rho_vass", "chr_kest_inger"], "goal": "Settle the map before the burn.", "conflict": "Every claimant loses something if the ruling is honest.", "outcome": "The route is opened to the fleet; Kest's claims unwind; Rho is paid in berth rights.", "depends_on": ["scn_cinder_lead"]},
                    ],
                },
                {
                    "id": "act_resolution", "title": "Resolution", "purpose": "resolution",
                    "scenes": [
                        {"id": "scn_shared_route", "title": "Through the Burn", "summary": "The fleet casts off on the shared route, the market threads perihelion whole, and Sable's ruling enters the burn articles as precedent.", "location_id": "loc_tether_docks", "character_ids": ["chr_sable_onuoha", "chr_rho_vass"], "goal": "See the fleet through the burn.", "conflict": "The route only holds if every ship flies it together.", "outcome": "The comet market survives its perihelion; the next orbit begins.", "depends_on": ["scn_burn_arbitration"]},
                    ],
                },
            ],
        },
    },
    # ------------------------------------------------------------------
    # 9. Historical monsoon-trade court
    # ------------------------------------------------------------------
    {
        "num": 9,
        "slug": "historical_monsoon_court",
        "gen_name": "v2_09_historical_monsoon_court",
        "evidence_summary": "The world, cast and storyboard satisfy the brief's pre-industrial monsoon-trade setting; deterministic validators are clean and there are no blocking defects.",
        "brief": {
            "title": "When the Wind Turns",
            "premise": "A harbour scribe in a monsoon-trade port must reconcile three foreign envoys' rival claims to the first sailing slot before the wind turns and the season is lost.",
            "genre": "historical fiction",
            "tone": "sumptuous and tense",
            "target_audience": "adult",
            "location_count": 4,
            "constraints": [
                "forbid:telegraph",
                "require:monsoon",
                "Setting is a pre-industrial Indian Ocean trade port; nothing later than the sixteenth century.",
                "max_locations:5",
            ],
        },
        "world": {
            "world_id": "wld_monsoon_court",
            "name": "The Monsoon Court",
            "description": "A great trade port whose whole calendar is set by the monsoon: fleets wait on the wind, sailing slots are worth fortunes, and the harbour court rules who sails first when the wind turns.",
            "locations": [
                {"id": "loc_harbour_office", "name": "The Harbour Office", "description": "The court's counting house where sailing-slot claims are entered in the harbour ledger."},
                {"id": "loc_envoy_house", "name": "The Envoy House", "description": "The lodging of foreign delegations, where rival claims are argued under the same roof."},
                {"id": "loc_pepper_warehouses", "name": "The Pepper Warehouses", "description": "The bonded cargo rows where the season's wealth waits on the wind."},
                {"id": "loc_pilot_ghat", "name": "The Pilot Ghat", "description": "The harbour steps where the master pilots read the sea and declare the monsoon turned."},
            ],
            "factions": [
                {"id": "fac_harbour_court", "name": "The Harbour Court", "description": "The scribes, weighers and slot-keepers who rule the sailing order.", "location_ids": ["loc_harbour_office"]},
                {"id": "fac_majlis", "name": "The Captains' Majlis", "description": "The dhow captains' council that bargains for the fleet's slots as one.", "location_ids": ["loc_envoy_house"]},
                {"id": "fac_pepper_factors", "name": "The Pepper Factors", "description": "The bonded merchants whose cargo makes the season and whose gifts smooth its way.", "location_ids": ["loc_pepper_warehouses"]},
            ],
            "rules": [
                {"id": "rul_wind_law", "statement": "No fleet may sail before the pilot ghat declares the monsoon turned.", "category": "social"},
                {"id": "rul_slot_order", "statement": "The first sailing slot belongs to the claim filed earliest in the harbour ledger.", "category": "social"},
                {"id": "rul_gift_register", "statement": "Every gift to a court official is entered in the gift register, or it is a bribe.", "category": "social"},
                {"id": "rul_oath_spice", "statement": "An oath sworn over pepper is binding before the harbour court.", "category": "social"},
            ],
            "history": [
                {"id": "evt_first_charter", "name": "The First Charter", "era": "The Founding Monsoons", "description": "The sailing slots were created to end the dock riots that met every turning wind.", "location_ids": ["loc_harbour_office"]},
                {"id": "evt_three_envoys", "name": "The Year of Three Envoys", "era": "The Middle Monsoons", "description": "Three delegations once deadlocked the court so long that the wind turned around them and the season was lost.", "location_ids": ["loc_envoy_house"]},
                {"id": "evt_ghat_oath", "name": "The Ghat Oath", "era": "The Middle Monsoons", "description": "After a pilot was bought to misread the sea, the ghat's declarations were bound to public rite.", "location_ids": ["loc_pilot_ghat"]},
            ],
            "conflicts": [
                {"id": "cnf_slot_rivalry", "name": "The First Slot", "description": "Three envoys claim to have filed in the same hour for the first sailing slot of the monsoon.", "faction_ids": ["fac_harbour_court", "fac_majlis"]},
                {"id": "cnf_gift_scandal", "name": "The Unregistered Gifts", "description": "Unregistered gifts have surfaced in the pepper warehouses, implicating the slot-keepers.", "faction_ids": ["fac_pepper_factors", "fac_harbour_court"]},
            ],
        },
        "characters": {
            "world_id": "wld_monsoon_court",
            "characters": [
                {
                    "id": "chr_deva_anai", "name": "Deva Anai", "role": "protagonist",
                    "description": "A junior scribe of the Harbour Office who keeps the slot ledger and can read an hour's filing in the grain of its ink.",
                    "personality_traits": ["scrupulous", "patient", "overlooked"],
                    "motivation": "To see the first slot go to whoever filed first, and only them.",
                    "goal": "Establish the true filing order before the wind turns.",
                    "flaw": "She believes the ledger is never wrong, which is exactly what the forgers count on.",
                    "internal_conflict": "Proving a forged filing means accusing the office that raised her.",
                    "external_conflict": "Three envoys, a factor and half the court want the audit to end inconclusive.",
                    "home_location_id": "loc_harbour_office", "faction_id": "fac_harbour_court",
                    "abilities": [{"name": "Ledger memory", "description": "Recites any entry she has ever copied and detects a hand that is not the clerk's own.", "category": "mental"}],
                    "arc": "Deva learns a ledger is only as honest as the hand allowed to write it.",
                },
                {
                    "id": "chr_suleiman_qadir", "name": "Suleiman Qadir", "role": "antagonist",
                    "description": "The richest of the pepper factors, who pre-dated a filing to buy the first slot for a cargo that cannot wait a second turn.",
                    "personality_traits": ["urbane", "generous in public", "cornered"],
                    "motivation": "To sail on the first wind before his cargo's buyers walk away.",
                    "goal": "Keep the first slot he bought until the monsoon is declared.",
                    "flaw": "He believes every record has a price because his always did.",
                    "internal_conflict": "The forged filing saved his season and may cost his name.",
                    "external_conflict": "Deva's audit can prove his entry was written out of order.",
                    "home_location_id": "loc_pepper_warehouses", "faction_id": "fac_pepper_factors",
                    "abilities": [{"name": "Factor's credit", "description": "Borrows against a season not yet sailed and makes creditors wait smiling.", "category": "social"}],
                    "arc": "Qadir must choose between the slot that saves his fortune and the name that carries it.",
                },
                {
                    "id": "chr_amara", "name": "Amara", "role": "supporting",
                    "description": "The senior pilot of the ghat, whose declaration of the turned wind is the only testimony the court cannot buy.",
                    "personality_traits": ["weathered", "incorruptible", "wry"],
                    "motivation": "To declare the wind honestly and see the fleet sail in the right order.",
                    "goal": "Settle the filing hour by the only record no one could forge: the sea's.",
                    "flaw": "She speaks in omen-rite that the court must take on faith.",
                    "internal_conflict": "Her declaration will end one envoy's season whichever way she calls it.",
                    "external_conflict": "Every claimant wants her declaration delayed until after their filing stands.",
                    "home_location_id": "loc_pilot_ghat", "faction_id": None,
                    "abilities": [{"name": "Wind-reading", "description": "Reads the turn of the monsoon a day before the sea shows it.", "category": "mental"}],
                    "arc": "Amara declares the wind on the honest hour and the court must follow.",
                },
            ],
            "relationships": [
                {"id": "rel_deva_amara", "source_character_id": "chr_deva_anai", "target_character_id": "chr_amara", "relationship_type": "ally", "description": "Amara's declaration can corroborate the true filing hour.", "conflict": "Her rite names the hour; Deva's ledger names the claimant."},
                {"id": "rel_deva_suleiman", "source_character_id": "chr_deva_anai", "target_character_id": "chr_suleiman_qadir", "relationship_type": "adversary", "description": "Deva's ink-reading can prove Qadir's filing was pre-dated.", "conflict": "Qadir's gifts to the court make the audit dangerous for her."},
            ],
        },
        "storyboard": {
            "world_id": "wld_monsoon_court",
            "title": "When the Wind Turns",
            "logline": "A harbour scribe proves which of three envoys truly filed first as the monsoon counts down the season.",
            "theme": "the honest hour",
            "acts": [
                {
                    "id": "act_setup", "title": "Setup", "purpose": "setup",
                    "scenes": [
                        {"id": "scn_three_claims", "title": "Three Envoys, One Hour", "summary": "At the Harbour Office, three envoys produce claims filed in the same hour for the first slot; Deva finds one entry's ink laid over another.", "location_id": "loc_harbour_office", "character_ids": ["chr_deva_anai"], "goal": "Order the rival filings.", "conflict": "Two of the three claims cannot both be true.", "outcome": "Deva flags the ledger for audit; the court splits.", "depends_on": []},
                        {"id": "scn_gift_surface", "title": "The Unregistered Gift", "summary": "In the Pepper Warehouses, a gift manifests without a register entry, tying Qadir's slot to an unentered favour.", "location_id": "loc_pepper_warehouses", "character_ids": ["chr_deva_anai", "chr_suleiman_qadir"], "goal": "Trace the unregistered gift.", "conflict": "An unentered gift is a bribe under the court's own rules.", "outcome": "The audit widens from the filings to the office itself.", "depends_on": ["scn_three_claims"]},
                    ],
                },
                {
                    "id": "act_rising", "title": "Rising Action", "purpose": "rising_action",
                    "scenes": [
                        {"id": "scn_ledger_audit", "title": "The Ink Beneath", "summary": "Deva audits the slot ledger and finds Qadir's entry written over a filed-and-scraped claim: the first slot was bought with a forged hour.", "location_id": "loc_harbour_office", "character_ids": ["chr_deva_anai"], "goal": "Prove the forged hour.", "conflict": "The proof condemns her own office.", "outcome": "The scraping is shown to the majlis; the court must rule by the true hour.", "depends_on": ["scn_gift_surface"]},
                        {"id": "scn_pilot_omen", "title": "The Pilot's Hour", "summary": "At the Pilot Ghat, Amara reads the sea and names the true filing hour by the swell that carried each envoy's boat to shore.", "location_id": "loc_pilot_ghat", "character_ids": ["chr_deva_anai", "chr_amara"], "goal": "Corroborate the true hour.", "conflict": "Her testimony is omen-rite, which the losing envoy will call superstition.", "outcome": "The sea's hour matches the scraped claim.", "depends_on": ["scn_ledger_audit"]},
                    ],
                },
                {
                    "id": "act_climax", "title": "Climax", "purpose": "climax",
                    "scenes": [
                        {"id": "scn_slot_ruling", "title": "The Ruling", "summary": "Before the Envoy House, Deva rules by the scraped claim and the pilot's hour; Qadir confesses rather than let the office burn with him.", "location_id": "loc_envoy_house", "character_ids": ["chr_deva_anai", "chr_suleiman_qadir", "chr_amara"], "goal": "Rule the first slot honestly.", "conflict": "Qadir's confession costs his season; silence costs his name.", "outcome": "The first slot goes to the true filer; the gift register is purged.", "depends_on": ["scn_pilot_omen"]},
                    ],
                },
                {
                    "id": "act_resolution", "title": "Resolution", "purpose": "resolution",
                    "scenes": [
                        {"id": "scn_monsoon_sails", "title": "The First Sail", "summary": "Amara declares the monsoon turned at the ghat, the rightful fleet sails first, and Deva's audit enters the harbour charter.", "location_id": "loc_pilot_ghat", "character_ids": ["chr_deva_anai", "chr_amara"], "goal": "See the season opened rightly.", "conflict": "The wind turns once; the ruling must hold when it does.", "outcome": "The fleet sails in the honest order; the monsoon court keeps its name.", "depends_on": ["scn_slot_ruling"]},
                    ],
                },
            ],
        },
    },
    # ------------------------------------------------------------------
    # 10. Folk horror moor parish
    # ------------------------------------------------------------------
    {
        "num": 10,
        "slug": "folk_horror_lantern_parish",
        "gen_name": "v2_10_folk_horror_lantern_parish",
        "evidence_summary": "The world, cast and storyboard satisfy the brief's lantern-keeping folk-horror setting; deterministic validators are clean and there are no blocking defects.",
        "brief": {
            "title": "Keep the Wick",
            "premise": "A new lamplighter in a moor parish learns that the parish's wall lanterns must never all go dark on the same night, and that last winter's ledger of lit nights has a page cut out.",
            "genre": "folk horror",
            "tone": "dread",
            "target_audience": "adult",
            "location_count": 4,
            "constraints": [
                "forbid:firearm",
                "require:lantern",
                "The parish is remote and pre-industrial; no firearms or engines.",
                "max_locations:5",
            ],
        },
        "world": {
            "world_id": "wld_lantern_parish",
            "name": "The Lantern Parish",
            "description": "A remote moor parish whose boundary wall carries a line of lanterns that must never all go dark on one night, for the bog walks when the light fails.",
            "locations": [
                {"id": "loc_lantern_wall", "name": "The Lantern Wall", "description": "The parish boundary wall, niched with lamps that are lit each dusk without fail."},
                {"id": "loc_moot_kirk", "name": "The Moot Kirk", "description": "The parish church where the ledger of lit nights is kept and the council sits."},
                {"id": "loc_bog_hollow", "name": "The Bog Hollow", "description": "The peat cuttings below the moor where lights drown and voices carry wrong."},
                {"id": "loc_keepers_croft", "name": "The Keeper's Croft", "description": "The lamplighter's cottage at the wall's foot, with its oil store and wick bench."},
            ],
            "factions": [
                {"id": "fac_lamp_wardens", "name": "The Lamp Wardens", "description": "The guild that keeps the wall, cuts the wicks and owes the parish its lit nights.", "location_ids": ["loc_keepers_croft", "loc_lantern_wall"]},
                {"id": "fac_moot_council", "name": "The Moot Council", "description": "The parish council that keeps the ledger and calls in the oil tithe.", "location_ids": ["loc_moot_kirk"]},
                {"id": "fac_turf_cutters", "name": "The Turf-Cutters", "description": "The families who cut peat in the bog and owe oil to the wall.", "location_ids": ["loc_bog_hollow"]},
            ],
            "rules": [
                {"id": "rul_never_dark", "statement": "Never may all the lanterns go dark on the same night; at least one wick must burn on the wall.", "category": "metaphysics"},
                {"id": "rul_lit_ledger", "statement": "Every lit night is entered in the ledger at the Moot Kirk; an unentered night did not happen.", "category": "social"},
                {"id": "rul_bog_line", "statement": "No lantern may be carried past the bog line after dusk.", "category": "social"},
                {"id": "rul_oil_tithe", "statement": "Every hearth owes a measure of oil to the wall; unpaid tithes are called in at midwinter.", "category": "social"},
            ],
            "history": [
                {"id": "evt_dark_winter", "name": "The Dark Winter", "era": "The Founding", "description": "In the parish's first year, every lamp failed on one night and half the hearths were empty by spring.", "location_ids": ["loc_bog_hollow"]},
                {"id": "evt_first_wick", "name": "The First Wick", "era": "The Founding", "description": "The wall was raised and the lantern rite begun so no night would ever be wholly dark again.", "location_ids": ["loc_lantern_wall"]},
                {"id": "evt_missing_page", "name": "The Missing Page", "era": "Last Winter", "description": "A page was cut from the ledger of lit nights, and no warden will say which night it held.", "location_ids": ["loc_moot_kirk"]},
            ],
            "conflicts": [
                {"id": "cnf_missing_night", "name": "The Missing Night", "description": "The cut page may hide a night the wall went dark, and the council and wardens each blame the other for the silence.", "faction_ids": ["fac_moot_council", "fac_lamp_wardens"]},
                {"id": "cnf_oil_shortfall", "name": "The Oil Shortfall", "description": "The turf-cutters owe oil and say the wardens over-count the call-in, while the wall burns short.", "faction_ids": ["fac_turf_cutters", "fac_lamp_wardens"]},
            ],
        },
        "characters": {
            "world_id": "wld_lantern_parish",
            "characters": [
                {
                    "id": "chr_wenna_crowe", "name": "Wenna Crowe", "role": "protagonist",
                    "description": "The new lamplighter, apprenticed into the wardens from outside the parish, who keeps the wick bench and asks questions the parish has stopped asking.",
                    "personality_traits": ["steady", "inquisitive", "unsentimental"],
                    "motivation": "To learn what the missing page hid before midwinter tests the wall again.",
                    "goal": "Find the truth of the dark night and keep every lantern lit through the winter.",
                    "flaw": "She needs proof before she will fear anything, and the bog does not give proof.",
                    "internal_conflict": "The rite she keeps is either sacred or superstition, and the missing page could say which.",
                    "external_conflict": "The council cut the page to keep the parish calm, and a calm parish is one that stops feeding the wall.",
                    "home_location_id": "loc_keepers_croft", "faction_id": "fac_lamp_wardens",
                    "abilities": [{"name": "Wick-craft", "description": "Keeps a flame alive in moor wind and driving wet better than any warden before her.", "category": "physical"}],
                    "arc": "Wenna learns that the missing page was cut to hide not the dark, but what the parish did about it.",
                },
                {
                    "id": "chr_reeve_toll", "name": "Reeve Toll", "role": "antagonist",
                    "description": "The parish reeve who cut the page from the ledger and has kept the parish's peace ever since.",
                    "personality_traits": ["grave", "controlled", "pragmatic"],
                    "motivation": "To keep the parish orderly and fed, whatever it takes not to know.",
                    "goal": "Keep the dark night buried through one more midwinter.",
                    "flaw": "He believes an orderly lie keeps more hearths lit than the truth.",
                    "internal_conflict": "He cut the page to save the parish, and cannot forgive himself for how well it worked.",
                    "external_conflict": "Wenna's questions threaten the silence that has kept the tithes coming.",
                    "home_location_id": "loc_moot_kirk", "faction_id": "fac_moot_council",
                    "abilities": [{"name": "Council writ", "description": "Writes and wields parish orders with a speed that outruns every question.", "category": "social"}],
                    "arc": "Toll's page is read back to him in front of the moot he deceived to save.",
                },
                {
                    "id": "chr_lob_ather", "name": "Lob Ather", "role": "supporting",
                    "description": "A turf-cutter who was out past the bog line on the missing night and saw the wall go dark.",
                    "personality_traits": ["gnarled", "fearful", "honest"],
                    "motivation": "To protect his family from the oil call-in and from what he saw.",
                    "goal": "Keep his hearth's oil until spring without betraying what he witnessed.",
                    "flaw": "Fear makes him lie first and tell the truth last.",
                    "internal_conflict": "His silence keeps his family safe and the parish blind.",
                    "external_conflict": "The reeve's writ can seize his oil, and the bog takes stragglers.",
                    "home_location_id": "loc_bog_hollow", "faction_id": "fac_turf_cutters",
                    "abilities": [{"name": "Bog-reading", "description": "Reads the bog's sounds and lights and tells which are only weather.", "category": "physical"}],
                    "arc": "Lob says aloud, once, what he saw, and the parish changes.",
                },
            ],
            "relationships": [
                {"id": "rel_wenna_lob", "source_character_id": "chr_wenna_crowe", "target_character_id": "chr_lob_ather", "relationship_type": "ally", "description": "Lob alone can tell Wenna what the missing page held.", "conflict": "His testimony costs him the council's mercy."},
                {"id": "rel_wenna_reeve", "source_character_id": "chr_wenna_crowe", "target_character_id": "chr_reeve_toll", "relationship_type": "adversary", "description": "Wenna's questions undo the silence Toll cut the page to keep.", "conflict": "Each believes their way is the only thing holding back the dark."},
            ],
        },
        "storyboard": {
            "world_id": "wld_lantern_parish",
            "title": "Keep the Wick",
            "logline": "A new lamplighter uncovers the night the wall went dark and relights it before the parish forgets why the lanterns matter.",
            "theme": "what the dark is owed",
            "acts": [
                {
                    "id": "act_setup", "title": "Setup", "purpose": "setup",
                    "scenes": [
                        {"id": "scn_first_round", "title": "The First Round", "summary": "On her first dusk round of the Lantern Wall, Wenna learns the rite by rote and counts one lamp niche that was never lit.", "location_id": "loc_lantern_wall", "character_ids": ["chr_wenna_crowe"], "goal": "Learn the round.", "conflict": "The unlit niche is not on any warden's list.", "outcome": "She logs it anyway, and the wardens take her book.", "depends_on": []},
                        {"id": "scn_torn_page", "title": "The Torn Page", "summary": "At the Moot Kirk, Wenna finds the page cut from the ledger of lit nights, and Reeve Toll orders her to let the record stand.", "location_id": "loc_moot_kirk", "character_ids": ["chr_wenna_crowe", "chr_reeve_toll"], "goal": "Account for the missing night.", "conflict": "An unentered night did not happen, and something is owed for it.", "outcome": "Wenna keeps a copy of the cut stub and starts asking.", "depends_on": ["scn_first_round"]},
                    ],
                },
                {
                    "id": "act_rising", "title": "Rising Action", "purpose": "rising_action",
                    "scenes": [
                        {"id": "scn_bog_witness", "title": "The Bog Witness", "summary": "At the Bog Hollow, Lob finally says what he saw: the wall dark for an hour, and the parish's answer carried out past the bog line.", "location_id": "loc_bog_hollow", "character_ids": ["chr_wenna_crowe", "chr_lob_ather"], "goal": "Learn what the page hid.", "conflict": "Naming it endangers Lob's family and the reeve's order alike.", "outcome": "Wenna learns the dark night happened, and how it was answered.", "depends_on": ["scn_torn_page"]},
                        {"id": "scn_oil_reckoning", "title": "The Oil Reckoning", "summary": "At the Keeper's Croft, Toll calls in the oil tithe early and short, knowing the midwinter weather will test the wall while questions are asked.", "location_id": "loc_keepers_croft", "character_ids": ["chr_wenna_crowe", "chr_reeve_toll", "chr_lob_ather"], "goal": "Keep the oil for the wall.", "conflict": "The call-in punishes the very witnesses the truth needs.", "outcome": "Wenna keeps her store; the parish sides against the cutters.", "depends_on": ["scn_bog_witness"]},
                    ],
                },
                {
                    "id": "act_climax", "title": "Climax", "purpose": "climax",
                    "scenes": [
                        {"id": "scn_dark_winter_eve", "title": "The Worst Night", "summary": "On the midwinter storm, the wind drowns lamp after lamp; Wenna keeps the last wick burning on the wall through the longest hour while the moot watches.", "location_id": "loc_lantern_wall", "character_ids": ["chr_wenna_crowe", "chr_lob_ather", "chr_reeve_toll"], "goal": "Keep one wick lit until dawn.", "conflict": "The storm wants the wall dark, and the parish is watching whether it matters.", "outcome": "One lamp burns through; the parish sees the price of the dark denied.", "depends_on": ["scn_oil_reckoning"]},
                    ],
                },
                {
                    "id": "act_resolution", "title": "Resolution", "purpose": "resolution",
                    "scenes": [
                        {"id": "scn_ledger_mended", "title": "The Amended Ledger", "summary": "At the Moot Kirk, the missing night is written back into the ledger, Toll answers for the cut page, and the tithe is reweighed in the open.", "location_id": "loc_moot_kirk", "character_ids": ["chr_wenna_crowe", "chr_reeve_toll", "chr_lob_ather"], "goal": "Restore the true record.", "conflict": "The truth frees the wardens and costs the council its silence.", "outcome": "The ledger is whole again; every hearth knows what the lanterns owe.", "depends_on": ["scn_dark_winter_eve"]},
                    ],
                },
            ],
        },
    },
]
