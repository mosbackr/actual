"""Import startups discovered from publication research into the database."""
import asyncio
import re
import uuid

from sqlalchemy import func, select

from app.db.session import async_session
from app.models.startup import (
    EntityType,
    EnrichmentStatus,
    Startup,
    StartupStage,
    StartupStatus,
)

STARTUPS = [
    # Batch 1: SF, NY, Boston, LA, Seattle
    ("Anysphere", "San Francisco", "CA", "US", "growth", "AI-powered developer tools platform behind the Cursor code editor", "https://www.cursor.com"),
    ("Physical Intelligence", "San Francisco", "CA", "US", "growth", "AI-powered robotics company building general-purpose robot foundation models", "https://www.physicalintelligence.company"),
    ("Mercor", "San Francisco", "CA", "US", "series_c", "AI-powered recruiting and talent marketplace platform", "https://www.mercor.com"),
    ("Scribe", "San Francisco", "CA", "US", "series_c", "AI-powered platform for auto-generating step-by-step guides and documentation", "https://scribehow.com"),
    ("Campfire", "San Francisco", "CA", "US", "series_b", "AI-powered fintech platform for financial operations", "https://www.campfire.co"),
    ("Gamma", "San Francisco", "CA", "US", "series_b", "AI-powered presentation and document creation platform", "https://gamma.app"),
    ("Rescale", "San Francisco", "CA", "US", "growth", "Digital engineering platform for high-performance computing simulation", "https://www.rescale.com"),
    ("Redpanda Data", "San Francisco", "CA", "US", "growth", "Real-time data streaming platform compatible with Apache Kafka", "https://www.redpanda.com"),
    ("Krea", "San Francisco", "CA", "US", "series_b", "Platform integrating multiple generative AI models for creative workflows", "https://www.krea.ai"),
    ("Distyl AI", "San Francisco", "CA", "US", "series_b", "Enterprise AI consulting and software platform", "https://www.distyl.ai"),
    ("Ambience Healthcare", "San Francisco", "CA", "US", "series_c", "AI operating system for healthcare documentation, coding, and workflows", "https://www.ambiencehealthcare.com"),
    ("Harvey", "San Francisco", "CA", "US", "growth", "AI-powered legal technology platform for law firms", "https://www.harvey.ai"),
    ("Listen Labs", "San Francisco", "CA", "US", "series_b", "Autonomous AI-powered market research platform", "https://www.listenlabs.com"),
    ("Glean", "San Francisco", "CA", "US", "growth", "AI-powered enterprise search and knowledge management platform", "https://www.glean.com"),
    ("Starbridge", "New York", "NY", "US", "series_a", "Go-to-market intelligence platform for government and education sales", "https://www.starbridge.com"),
    ("ExaCare", "New York", "NY", "US", "series_a", "AI-powered software for assisted living facility admissions and care", "https://www.exacare.com"),
    ("Graphite", "New York", "NY", "US", "series_b", "AI-powered code review and developer productivity platform", "https://graphite.dev"),
    ("Kalshi", "New York", "NY", "US", "growth", "Exchange platform for trading on real-world event outcomes", "https://kalshi.com"),
    ("Bilt Rewards", "New York", "NY", "US", "growth", "Loyalty and rewards platform for residential rent payments", "https://www.biltrewards.com"),
    ("Esusu", "New York", "NY", "US", "series_c", "Financial technology platform leveraging data to help renters build credit", "https://www.esusu.com"),
    ("Cyera", "New York", "NY", "US", "growth", "AI-powered data security and data loss prevention platform", "https://www.cyera.io"),
    ("Avallon", "New York", "NY", "US", "seed", "Agentic AI platform for insurance claims operations automation", "https://www.avallon.ai"),
    ("FINNY", "New York", "NY", "US", "series_a", "AI-powered prospecting platform for financial advisors", "https://www.finny.com"),
    ("Marble Health", "New York", "NY", "US", "series_a", "Mental health platform providing therapy and support for teens", "https://www.marblehealth.com"),
    ("Dux Security", "New York", "NY", "US", "seed", "Agentic exposure management platform for cybersecurity", "https://www.duxsecurity.com"),
    ("7AI", "Boston", "MA", "US", "series_a", "AI-powered cybersecurity platform for network and computer security", "https://www.7ai.com"),
    ("Hillstar Bio", "Boston", "MA", "US", "series_a", "Precision immunotherapies for autoimmune diseases", "https://www.hillstarbio.com"),
    ("Somite AI", "Boston", "MA", "US", "series_a", "Foundation models for human cells to accelerate cell therapy development", "https://www.somite.ai"),
    ("PhaseV", "Boston", "MA", "US", "series_a", "Machine learning platform to optimize clinical trial design", "https://www.phasev.com"),
    ("Method AI", "Boston", "MA", "US", "series_a", "AI-powered surgical guidance and planning technology", "https://www.method.ai"),
    ("Eleos Health", "Boston", "MA", "US", "series_c", "Voice analysis and NLP platform for behavioral health treatment", "https://eleos.health"),
    ("Cohere Health", "Boston", "MA", "US", "series_c", "AI-powered prior authorization platform for healthcare", "https://www.coherehealth.com"),
    ("VEIR", "Boston", "MA", "US", "series_b", "High-temperature superconducting power line technology", "https://www.veir.com"),
    ("Liquid AI", "Boston", "MA", "US", "series_a", "AI foundation model company building liquid neural networks", "https://www.liquid.ai"),
    ("AllRock Bio", "Boston", "MA", "US", "series_a", "Biopharmaceutical company developing novel protein therapeutics", "https://www.allrockbio.com"),
    ("Atalanta Therapeutics", "Boston", "MA", "US", "series_b", "RNA-based therapeutics for neurological diseases", "https://www.atalantatx.com"),
    ("BuildOps", "Los Angeles", "CA", "US", "series_c", "Construction tech platform for commercial contractors", "https://www.buildops.com"),
    ("Rain", "Los Angeles", "CA", "US", "series_b", "Earned wage access and financial wellness platform", "https://www.rain.us"),
    ("Whatnot", "Los Angeles", "CA", "US", "growth", "Livestream shopping and marketplace platform for collectibles", "https://www.whatnot.com"),
    ("Wolf Games", "Los Angeles", "CA", "US", "series_a", "Generative AI gaming studio building cinematic interactive experiences", "https://www.wolfgames.com"),
    ("Pirros", "Los Angeles", "CA", "US", "series_a", "Architecture and engineering design detail management software", "https://www.pirros.com"),
    ("Knox Systems", "Los Angeles", "CA", "US", "series_a", "Security platform helping organizations achieve FedRAMP authorization", "https://www.knoxsystems.com"),
    ("Daydream", "Los Angeles", "CA", "US", "series_a", "AI-native SEO agency and content marketing platform", "https://www.daydream.com"),
    ("Jimini Health", "Los Angeles", "CA", "US", "seed", "Clinician-supervised AI platform for behavioral health", "https://www.jiminihealth.com"),
    ("Entire", "Seattle", "WA", "US", "seed", "Developer platform built by former GitHub CEO", "https://www.entire.dev"),
    ("Supio", "Seattle", "WA", "US", "series_b", "AI-powered legal research platform for attorneys", "https://www.supio.com"),
    ("Overland AI", "Seattle", "WA", "US", "series_a", "Autonomous ground vehicle technology for defense", "https://www.overlandai.com"),
    ("Factal", "Seattle", "WA", "US", "series_a", "Real-time global event monitoring and crisis alert platform", "https://www.factal.com"),
    ("Xbow", "Seattle", "WA", "US", "series_c", "Autonomous cybersecurity platform for automated penetration testing", "https://www.xbow.com"),
    ("Zap Energy", "Seattle", "WA", "US", "series_a", "Compact scalable fusion energy systems", "https://www.zapenergy.com"),
    # Batch 2: Austin, Chicago, Miami, Denver, DC, San Jose
    ("Apptronik", "Austin", "TX", "US", "series_a", "Humanoid robotics company building general-purpose robots", "https://apptronik.com"),
    ("Saronic", "Austin", "TX", "US", "series_c", "Autonomous surface vessels and drone boats for defense", "https://www.saronic.com"),
    ("NinjaOne", "Austin", "TX", "US", "series_c", "Endpoint management and security platform for IT teams", "https://www.ninjaone.com"),
    ("Base Power", "Austin", "TX", "US", "series_c", "Distributed energy company building resilient power infrastructure", "https://www.basepower.com"),
    ("Colossal Biosciences", "Austin", "TX", "US", "series_c", "De-extinction and conservation genetics using gene editing", "https://colossal.com"),
    ("Extropic", "Austin", "TX", "US", "seed", "Physics-based computing for energy-efficient AI", "https://www.extropic.ai"),
    ("QuoteWell", "Austin", "TX", "US", "series_a", "AI-powered commercial insurance wholesale brokerage", "https://www.quotewell.com"),
    ("Ambiq", "Austin", "TX", "US", "growth", "Ultra-low-power semiconductor solutions for edge intelligence", "https://ambiq.com"),
    ("Qualified Health", "Chicago", "IL", "US", "series_a", "AI evaluation and implementation platform for health systems", "https://www.qualifiedhealth.ai"),
    ("Pathos AI", "Chicago", "IL", "US", "series_a", "AI-powered oncology drug discovery platform", "https://www.pathosai.com"),
    ("Prenosis", "Chicago", "IL", "US", "series_b", "FDA-authorized AI-driven clinical decision support for sepsis", "https://www.prenosis.com"),
    ("Formic Technologies", "Chicago", "IL", "US", "series_a", "Robotics-as-a-service platform for manufacturing", "https://formic.co"),
    ("Arturo", "Chicago", "IL", "US", "series_b", "AI-powered property intelligence for insurance carriers", "https://www.arturo.ai"),
    ("project44", "Chicago", "IL", "US", "growth", "Cloud-based supply chain visibility and tracking platform", "https://www.project44.com"),
    ("Keeper Security", "Chicago", "IL", "US", "series_b", "Zero-trust cybersecurity platform for password management", "https://www.keepersecurity.com"),
    ("LogicGate", "Chicago", "IL", "US", "series_b", "Governance, risk, and compliance automation platform", "https://www.logicgate.com"),
    ("ActiveCampaign", "Chicago", "IL", "US", "growth", "Customer experience automation for email marketing and CRM", "https://www.activecampaign.com"),
    ("OpenEvidence", "Miami", "FL", "US", "series_c", "AI-powered medical evidence platform for doctors", "https://www.openevidence.com"),
    ("Exowatt", "Miami", "FL", "US", "series_a", "Clean energy systems powering data centers with renewables", "https://www.exowatt.com"),
    ("Papa", "Miami", "FL", "US", "series_b", "Elder care platform connecting seniors with companionship", "https://www.papa.com"),
    ("Neocis", "Miami", "FL", "US", "series_b", "Medical robotics with Yomi robotic dental surgery system", "https://www.neocis.com"),
    ("Lumu Technologies", "Miami", "FL", "US", "series_b", "Cybersecurity platform for network threat detection", "https://lumu.io"),
    ("Pipe", "Miami", "FL", "US", "series_b", "Platform turning recurring revenue into upfront capital", "https://pipe.com"),
    ("Crusoe Energy Systems", "Denver", "CO", "US", "growth", "Clean compute infrastructure powering AI with stranded energy", "https://www.crusoe.ai"),
    ("Strive Health", "Denver", "CO", "US", "series_b", "Value-based kidney care management platform", "https://www.strivehealth.com"),
    ("MagicSchool AI", "Denver", "CO", "US", "series_b", "AI assistant platform for educators and schools", "https://www.magicschool.ai"),
    ("Peak Energy", "Denver", "CO", "US", "series_a", "Sodium-ion battery storage for grid-scale energy", "https://www.peakenergy.com"),
    ("Automox", "Denver", "CO", "US", "series_b", "Cloud-native IT endpoint management and automated patching", "https://www.automox.com"),
    ("Last Energy", "Washington", "DC", "US", "series_c", "Modular nuclear energy delivering turnkey micro-reactors", "https://www.lastenergy.com"),
    ("Sublime Security", "Washington", "DC", "US", "series_c", "AI-powered email security for enterprise threat detection", "https://sublimesecurity.com"),
    ("Hydrosat", "Washington", "DC", "US", "series_b", "Agricultural intelligence using thermal satellite data", "https://www.hydrosat.com"),
    ("Shield AI", "Washington", "DC", "US", "growth", "AI-powered autonomous systems for defense", "https://shield.ai"),
    ("Shift5", "Washington", "DC", "US", "series_b", "OT cybersecurity for defense and transportation", "https://www.shift5.io"),
    ("Etched", "San Jose", "CA", "US", "series_b", "AI hardware developing specialized chips for ML", "https://www.etched.com"),
    ("SambaNova Systems", "San Jose", "CA", "US", "growth", "Full-stack AI platform with custom processors", "https://sambanova.ai"),
    ("Cerebras Systems", "San Jose", "CA", "US", "growth", "Wafer-scale AI compute systems", "https://www.cerebras.net"),
    ("Verkada", "San Jose", "CA", "US", "growth", "Cloud-based physical security platform with AI cameras", "https://www.verkada.com"),
    ("Lightmatter", "San Jose", "CA", "US", "series_c", "Photonic computing and interconnect for AI data centers", "https://lightmatter.co"),
    ("Ayar Labs", "San Jose", "CA", "US", "series_b", "Optical interconnect technology for data centers", "https://ayarlabs.com"),
    # Batch 3: San Diego, Atlanta, Dallas, Houston, Philly, Minneapolis, Detroit, Pittsburgh, Nashville, RDU
    ("Drata", "San Diego", "CA", "US", "series_c", "Trust management platform automating security compliance", "https://drata.com"),
    ("Element Biosciences", "San Diego", "CA", "US", "growth", "Genetic analysis tools including DNA sequencing", "https://elementbiosciences.com"),
    ("Iambic", "San Diego", "CA", "US", "series_b", "AI-driven drug discovery and therapeutics", "https://iambic.ai"),
    ("Gretel", "San Diego", "CA", "US", "series_b", "AI-powered synthetic data platform for privacy-safe ML", "https://gretel.ai"),
    ("Biolinq", "San Diego", "CA", "US", "series_c", "Continuous glucose monitoring biosensor technology", "https://biolinq.com"),
    ("Candid Therapeutics", "San Diego", "CA", "US", "series_a", "Therapies for autoimmune diseases", "https://candidrx.com"),
    ("Flock Safety", "Atlanta", "GA", "US", "growth", "Public safety technology with license plate reading cameras", "https://www.flocksafety.com"),
    ("OneTrust", "Atlanta", "GA", "US", "growth", "Trust intelligence platform for data governance and compliance", "https://www.onetrust.com"),
    ("Tractian", "Atlanta", "GA", "US", "series_c", "AI-powered industrial maintenance and asset monitoring", "https://tractian.com"),
    ("Stord", "Atlanta", "GA", "US", "growth", "Cloud supply chain platform combining software with logistics", "https://www.stord.com"),
    ("Greenlight", "Atlanta", "GA", "US", "growth", "Fintech teaching kids financial literacy with debit cards", "https://greenlight.com"),
    ("Salesloft", "Atlanta", "GA", "US", "growth", "Sales engagement and revenue operations SaaS platform", "https://salesloft.com"),
    ("HighLevel", "Dallas", "TX", "US", "growth", "All-in-one sales and marketing platform for agencies", "https://gohighlevel.com"),
    ("o9 Solutions", "Dallas", "TX", "US", "growth", "AI-powered integrated business planning and supply chain", "https://o9solutions.com"),
    ("Island", "Dallas", "TX", "US", "growth", "Secure enterprise web browser for workplace activity", "https://island.io"),
    ("Compass Datacenters", "Dallas", "TX", "US", "growth", "Hyperscale data center design and operations", "https://compassdatacenters.com"),
    ("Fervo Energy", "Houston", "TX", "US", "growth", "Next-generation geothermal energy technology", "https://fervoenergy.com"),
    ("Axiom Space", "Houston", "TX", "US", "series_c", "Commercial space station infrastructure", "https://axiomspace.com"),
    ("Venus Aerospace", "Houston", "TX", "US", "series_a", "Hypersonic aircraft and rocket engine propulsion", "https://venusaero.com"),
    ("Intuitive Machines", "Houston", "TX", "US", "growth", "Lunar lander and orbital transfer vehicle developer", "https://intuitivemachines.com"),
    ("Hello Alice", "Houston", "TX", "US", "series_c", "Financial services and grant platform for small businesses", "https://helloalice.com"),
    ("HighRadius", "Houston", "TX", "US", "series_c", "AI-powered accounts receivable and treasury management", "https://highradius.com"),
    ("Proscia", "Philadelphia", "PA", "US", "growth", "AI-powered digital pathology for lab diagnostics", "https://www.proscia.com"),
    ("HealthVerity", "Philadelphia", "PA", "US", "growth", "Healthcare data discovery and licensing for clinical trials", "https://healthverity.com"),
    ("ConnectDER", "Philadelphia", "PA", "US", "growth", "Meter collar technology for distributed energy connections", "https://connectder.com"),
    ("Interius BioTherapeutics", "Philadelphia", "PA", "US", "series_a", "In vivo cell and gene therapy for blood cancers", "https://interiusbio.com"),
    ("NetSPI", "Minneapolis", "MN", "US", "growth", "Enterprise security testing and attack surface management", "https://netspi.com"),
    ("Niron Magnetics", "Minneapolis", "MN", "US", "series_b", "Sustainable permanent magnets using iron nitride", "https://nironmagnetics.com"),
    ("Sezzle", "Minneapolis", "MN", "US", "growth", "Buy-now-pay-later fintech with interest-free installments", "https://sezzle.com"),
    ("StockX", "Detroit", "MI", "US", "growth", "Live marketplace for sneakers and collectibles", "https://stockx.com"),
    ("Voxel51", "Detroit", "MI", "US", "series_b", "Computer vision data management for AI developers", "https://voxel51.com"),
    ("MemryX", "Detroit", "MI", "US", "series_b", "Edge AI accelerator chip for automotive and robotics", "https://memryx.com"),
    ("May Mobility", "Detroit", "MI", "US", "series_c", "Autonomous vehicle and urban mobility technology", "https://maymobility.com"),
    ("Skild AI", "Pittsburgh", "PA", "US", "series_b", "Foundational software enabling robots to learn physical tasks", "https://skild.ai"),
    ("Abridge", "Pittsburgh", "PA", "US", "growth", "AI transforming patient-clinician conversations into notes", "https://abridge.com"),
    ("Niche.com", "Pittsburgh", "PA", "US", "series_c", "Platform for researching US colleges and schools", "https://niche.com"),
    ("Thyme Care", "Nashville", "TN", "US", "growth", "Comprehensive cancer care support platform", "https://thymecare.com"),
    ("Imagine Pediatrics", "Nashville", "TN", "US", "series_b", "Virtual care for children with complex medical needs", "https://imaginepediatrics.org"),
    ("Built Technologies", "Nashville", "TN", "US", "series_b", "Financial technology platform for construction lending", "https://getbuilt.com"),
    ("Pendo", "Raleigh-Durham", "NC", "US", "growth", "Product experience platform for user behavior analytics", "https://www.pendo.io"),
    ("Teamworks", "Raleigh-Durham", "NC", "US", "growth", "Sports operations platform for team management", "https://teamworks.com"),
    ("Restor3d", "Raleigh-Durham", "NC", "US", "series_c", "3D-printed orthopedic implants and surgical solutions", "https://restor3d.com"),
    # Batch 4: SLC, Portland, Phoenix, Columbus, Indy, STL, Baltimore, Tampa, Charlotte, LV, Cincy, KC
    ("Filevine", "Salt Lake City", "UT", "US", "growth", "AI-native operating system for legal services", "https://www.filevine.com"),
    ("Awardco", "Salt Lake City", "UT", "US", "series_b", "Employee recognition and rewards platform", "https://www.awardco.com"),
    ("PassiveLogic", "Salt Lake City", "UT", "US", "series_c", "Generative autonomy platform for building systems", "https://www.passivelogic.com"),
    ("Zanskar", "Salt Lake City", "UT", "US", "series_c", "AI for geothermal energy exploration", "https://www.zanskar.com"),
    ("Hydrolix", "Portland", "OR", "US", "series_c", "Streaming data lake for high-volume log data", "https://www.hydrolix.io"),
    ("ConductorOne", "Portland", "OR", "US", "series_b", "AI-native identity security platform", "https://www.conductorone.com"),
    ("Boulder Care", "Portland", "OR", "US", "series_c", "Digital clinic for substance use disorder treatment", "https://www.boulder.care"),
    ("Customer.io", "Portland", "OR", "US", "growth", "Customer engagement and marketing automation platform", "https://customer.io"),
    ("Paradox", "Phoenix", "AZ", "US", "series_c", "AI conversational recruiting platform", "https://www.paradox.ai"),
    ("Persefoni", "Phoenix", "AZ", "US", "series_c", "Climate management and carbon accounting platform", "https://www.persefoni.com"),
    ("Solera Health", "Phoenix", "AZ", "US", "growth", "Digital health platform for chronic condition management", "https://www.soleranetwork.com"),
    ("Root Insurance", "Columbus", "OH", "US", "growth", "AI-powered auto insurance platform", "https://www.joinroot.com"),
    ("Loop Returns", "Columbus", "OH", "US", "series_b", "Returns automation for Shopify e-commerce", "https://www.loopreturns.com"),
    ("Path Robotics", "Columbus", "OH", "US", "series_b", "Autonomous robotic welding using machine learning", "https://www.path-robotics.com"),
    ("Forge Biologics", "Columbus", "OH", "US", "series_b", "Gene therapy CDMO for genetic medicines", "https://www.forgebiologics.com"),
    ("Branch Insurance", "Columbus", "OH", "US", "series_c", "Bundled home, auto, and renter insurance", "https://www.ourbranch.com"),
    ("Formstack", "Indianapolis", "IN", "US", "growth", "No-code workplace productivity and workflow automation", "https://www.formstack.com"),
    ("Encamp", "Indianapolis", "IN", "US", "series_c", "Environmental compliance platform", "https://www.encamp.com"),
    ("Scale Computing", "Indianapolis", "IN", "US", "growth", "Unified cloud infrastructure for servers and storage", "https://www.scalecomputing.com"),
    ("Wugen", "St. Louis", "MO", "US", "series_c", "Off-the-shelf CAR-T cellular therapies for cancer", "https://www.wugen.com"),
    ("Intramotev", "St. Louis", "MO", "US", "series_a", "Battery-electric autonomous railcar technology", "https://www.intramotev.com"),
    ("NewLeaf Symbiotics", "St. Louis", "MO", "US", "growth", "Agricultural biotech using beneficial microbes", "https://www.newleafsym.com"),
    ("Delfi Diagnostics", "Baltimore", "MD", "US", "series_b", "Blood test for early cancer detection using fragmentomics", "https://www.delfi.com"),
    ("ZeroFOX", "Baltimore", "MD", "US", "growth", "Digital risk protection and cybersecurity", "https://www.zerofox.com"),
    ("Protenus", "Baltimore", "MD", "US", "series_c", "AI monitoring healthcare compliance and fraud", "https://www.protenus.com"),
    ("ReliaQuest", "Tampa", "FL", "US", "growth", "AI-driven cybersecurity platform", "https://www.reliaquest.com"),
    ("Rewst", "Tampa", "FL", "US", "series_b", "Robotic process automation for MSPs", "https://www.rewst.io"),
    ("Slide Insurance", "Tampa", "FL", "US", "series_a", "AI-powered homeowners insurance provider", "https://www.slideinsurance.com"),
    ("Aiwyn", "Charlotte", "NC", "US", "series_b", "AI automation for accounting firm billing", "https://www.aiwyn.ai"),
    ("isolved", "Charlotte", "NC", "US", "growth", "Human capital management for HR and payroll", "https://www.isolvedhcm.com"),
    ("Flexential", "Charlotte", "NC", "US", "growth", "Hybrid IT solutions with colocation and cloud", "https://www.flexential.com"),
    ("TensorWave", "Las Vegas", "NV", "US", "series_a", "On-demand GPU cloud platform for AI workloads", "https://www.tensorwave.com"),
    ("Hubble Network", "Las Vegas", "NV", "US", "series_b", "Satellite-powered IoT connecting Bluetooth devices", "https://www.hubble.com"),
    ("Luma Financial Technologies", "Cincinnati", "OH", "US", "series_c", "Structured products platform for banks and brokers", "https://www.lumafintech.com"),
    ("Electrada", "Cincinnati", "OH", "US", "series_b", "EV charging infrastructure for commercial fleets", "https://www.electrada.com"),
    ("Startland News", "Kansas City", "MO", "US", "seed", "Startup news and community platform", "https://www.startlandnews.com"),
    ("Laravel", "Kansas City", "MO", "US", "series_a", "Open-source PHP web application framework", "https://www.laravel.com"),
    # Batch 5: Birmingham, Madison, Omaha, Sacramento, Oakland, Orlando, Cleveland, Irvine, SA, Jax, FW, OKC, Louisville, Milwaukee, NOLA, Memphis
    ("Linq", "Birmingham", "AL", "US", "series_a", "AI-powered messaging and digital business card platform", "https://linqapp.com"),
    ("ResBiotic", "Birmingham", "AL", "US", "series_a", "Microbiome-based probiotic supplements for respiratory health", "https://resbiotic.com"),
    ("CompanyCam", "Omaha", "NE", "US", "series_c", "Construction site documentation and project management", "https://www.companycam.com"),
    ("Fivetran", "Oakland", "CA", "US", "growth", "Automated data movement platform", "https://fivetran.com"),
    ("LaunchDarkly", "Oakland", "CA", "US", "series_c", "Feature management platform for software releases", "https://launchdarkly.com"),
    ("Everlaw", "Oakland", "CA", "US", "series_c", "Cloud-native e-discovery platform for legal teams", "https://everlaw.com"),
    ("Olipop", "Oakland", "CA", "US", "series_c", "Sparkling tonics with plant fiber and prebiotics", "https://drinkolipop.com"),
    ("Elicit", "Oakland", "CA", "US", "seed", "AI research assistant for scientific literature review", "https://elicit.com"),
    ("Kore.ai", "Orlando", "FL", "US", "series_c", "AI platform for enterprise virtual assistants", "https://kore.ai"),
    ("NUVIEW", "Orlando", "FL", "US", "series_a", "Commercial LiDAR satellite constellation", "https://nuview.space"),
    ("Champ Titles", "Cleveland", "OH", "US", "series_b", "Digital vehicle title and registration platform", ""),
    ("Turion Space", "Irvine", "CA", "US", "series_a", "DROID satellites for space domain awareness", "https://turionspace.com"),
    ("Syntiant", "Irvine", "CA", "US", "series_b", "Ultra-low-power AI semiconductors for edge computing", "https://syntiant.com"),
    ("Plus One Robotics", "San Antonio", "TX", "US", "series_a", "AI-powered vision and robotics for e-commerce fulfillment", ""),
    ("FloatMe", "San Antonio", "TX", "US", "series_a", "Early paycheck access and financial wellness fintech", ""),
    ("Clearsense", "Jacksonville", "FL", "US", "growth", "AI platform for healthcare data governance", ""),
    ("Finxact", "Jacksonville", "FL", "US", "series_a", "Enterprise cloud core banking-as-a-service", "https://finxact.com"),
    ("Linear Labs", "Fort Worth", "TX", "US", "series_a", "Next-generation electric vehicle motors", ""),
    ("JuneBrain", "New Orleans", "LA", "US", "seed", "AI-driven OCT headsets for neurological monitoring", "https://junebrain.com"),
    ("PosiGen", "New Orleans", "LA", "US", "growth", "Solar energy for low-to-moderate income homeowners", "https://posigen.com"),
    ("Advano", "New Orleans", "LA", "US", "series_a", "Advanced silicon materials for batteries", "https://advano.io"),
    ("Gravity Diagnostics", "Louisville", "KY", "US", "series_a", "Advanced diagnostics for substance use disorder testing", ""),
    ("Bespoken Spirits", "Louisville", "KY", "US", "series_a", "Sustainable spirits production technology", ""),
    # Batch 6: International
    ("Cohere", "Toronto", None, "Canada", "growth", "Enterprise AI platform building large language models", "https://cohere.com"),
    ("StackAdapt", "Toronto", None, "Canada", "growth", "AI-powered programmatic advertising platform", "https://www.stackadapt.com"),
    ("Waabi", "Toronto", None, "Canada", "series_b", "AI-powered autonomous driving for trucking", "https://waabi.ai"),
    ("Ada", "Toronto", None, "Canada", "series_c", "AI-native platform for automating customer service", "https://www.ada.cx"),
    ("Ideogram", "Toronto", None, "Canada", "series_a", "AI image generation for creative professionals", "https://ideogram.ai"),
    ("Tenstorrent", "Toronto", None, "Canada", "series_c", "AI hardware and chip design for next-gen computing", "https://tenstorrent.com"),
    ("Clio", "Vancouver", None, "Canada", "growth", "Cloud-based legal practice management software", "https://www.clio.com"),
    ("General Fusion", "Vancouver", None, "Canada", "series_c", "Magnetized target fusion energy technology", "https://generalfusion.com"),
    ("AbCellera", "Vancouver", None, "Canada", "growth", "AI-powered antibody discovery for drug development", "https://www.abcellera.com"),
    ("Isomorphic Labs", "London", None, "UK", "series_a", "AI-driven drug discovery leveraging AlphaFold", "https://www.isomorphiclabs.com"),
    ("ElevenLabs", "London", None, "UK", "series_c", "AI voice synthesis and text-to-speech platform", "https://elevenlabs.io"),
    ("Wayve", "London", None, "UK", "series_c", "Autonomous driving AI for urban robotaxis", "https://wayve.ai"),
    ("Synthesia", "London", None, "UK", "series_c", "AI-powered video generation for enterprise communications", "https://www.synthesia.io"),
    ("Revolut", "London", None, "UK", "growth", "Digital banking and financial services super-app", "https://www.revolut.com"),
    ("n8n", "Berlin", None, "Germany", "series_c", "Workflow automation platform combining AI with processes", "https://n8n.io"),
    ("Mistral AI", "Paris", None, "France", "series_c", "Large language model platform for enterprise AI", "https://mistral.ai"),
    ("Pennylane", "Paris", None, "France", "series_c", "Financial operating system for European SMEs", "https://www.pennylane.com"),
    ("Pigment", "Paris", None, "France", "series_c", "AI-powered business planning platform", "https://www.gopigment.com"),
    ("Hugging Face", "Paris", None, "France", "series_c", "Open-source ML and NLP model hosting platform", "https://huggingface.co"),
    ("Silicon Canals", "Amsterdam", None, "Netherlands", "seed", "European startup and tech news platform", "https://siliconcanals.com"),
    ("Picnic", "Amsterdam", None, "Netherlands", "growth", "App-based online supermarket with EV delivery", "https://www.picnic.app"),
    ("Finom", "Amsterdam", None, "Netherlands", "series_c", "Unified financial platform for European SMEs", "https://finom.co"),
    ("Lovable", "Stockholm", None, "Sweden", "series_a", "AI platform for building apps through conversation", "https://lovable.dev"),
    ("Neko Health", "Stockholm", None, "Sweden", "series_b", "Preventive health scanning with AI diagnostics", "https://www.nekohealth.com"),
    ("Einride", "Stockholm", None, "Sweden", "series_c", "Autonomous electric freight transport platform", "https://www.einride.tech"),
    ("Thunes", "Singapore", None, "Singapore", "series_c", "Global cross-border payments network", "https://www.thunes.com"),
    ("Bolttech", "Singapore", None, "Singapore", "series_c", "Insurance technology for embedded protection", "https://www.bolttech.io"),
    ("Nium", "Singapore", None, "Singapore", "series_c", "Global payment infrastructure for banks and fintechs", "https://www.nium.com"),
    ("Airwallex", "Singapore", None, "Singapore", "growth", "Cross-border payment infrastructure", "https://www.airwallex.com"),
    ("Canva", "Sydney", None, "Australia", "growth", "Cloud-based graphic design platform", "https://www.canva.com"),
    ("SafetyCulture", "Sydney", None, "Australia", "growth", "Workplace operations and safety inspection platform", "https://safetyculture.com"),
    ("Groww", "Bangalore", None, "India", "growth", "Online investment platform for stocks and mutual funds", "https://groww.in"),
    ("Sarvam AI", "Bangalore", None, "India", "series_a", "India's sovereign AI platform building homegrown LLMs", "https://www.sarvam.ai"),
    ("Quantum Machines", "Tel Aviv", None, "Israel", "series_c", "Quantum computing orchestration platform", "https://www.quantum-machines.co"),
    ("Eon", "Tel Aviv", None, "Israel", "series_c", "Cloud-based medical imaging AI for early disease detection", "https://www.eon.health"),
    ("Omie", "Sao Paulo", None, "Brazil", "series_c", "Cloud-based ERP for small and medium businesses", "https://www.omie.com.br"),
    ("Blip", "Sao Paulo", None, "Brazil", "series_c", "AI-powered conversational platform for enterprise", "https://www.blip.ai"),
    ("Klar", "Mexico City", None, "Mexico", "series_c", "Digital banking for Mexican consumers", "https://www.klar.mx"),
    ("Belvo", "Mexico City", None, "Mexico", "series_a", "Open finance API platform for Latin America", "https://belvo.com"),
]

VALID_STAGES = {"pre_seed", "seed", "series_a", "series_b", "series_c", "growth"}


def slugify(name):
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


async def main():
    print(f"Importing {len(STARTUPS)} startups from publication research...")

    async with async_session() as db:
        created = 0
        skipped_dup = 0

        for name, city, state, country, stage, desc, website in STARTUPS:
            name = name.strip()
            if not name:
                continue

            # Validate stage
            if stage not in VALID_STAGES:
                stage = "seed"

            # Dedup by name
            existing = await db.execute(
                select(Startup).where(func.lower(Startup.name) == name.lower())
            )
            if existing.scalar_one_or_none():
                skipped_dup += 1
                continue

            # Check slug
            slug = slugify(name)
            slug_check = await db.execute(
                select(Startup).where(Startup.slug == slug)
            )
            if slug_check.scalar_one_or_none():
                slug = f"{slug}-{created}"

            startup = Startup(
                name=name,
                slug=slug,
                description=desc or f"{name} startup",
                website_url=website or None,
                stage=StartupStage(stage),
                status=StartupStatus.approved,
                entity_type=EntityType.startup,
                enrichment_status=EnrichmentStatus.none,
                location_city=city,
                location_state=state,
                location_country=country or "US",
                form_sources=["publication_research"],
                data_sources={
                    "name": "publication_research",
                    "description": "publication_research",
                    "stage": "publication_research",
                },
            )
            db.add(startup)
            created += 1

            if created % 50 == 0:
                print(f"  Progress: {created} created...")

        await db.commit()
        print(f"Done: {created} created, {skipped_dup} duplicates skipped")


asyncio.run(main())
