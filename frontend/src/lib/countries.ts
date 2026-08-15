// Le fournisseur donne un nom de pays complet ("Spain"), pas un code ISO (voir
// scripts/enrich_players.py cote backend). Mapping construit pour couvrir les
// nationalites courantes du circuit pro - liste non exhaustive, fallback sur le texte
// brut si non trouve plutot que de planter.
const COUNTRY_TO_ISO2: Record<string, string> = {
  Spain: 'ES', Serbia: 'RS', Switzerland: 'CH', Russia: 'RU', Italy: 'IT',
  France: 'FR', Germany: 'DE', 'United States': 'US', USA: 'US',
  'Great Britain': 'GB', 'United Kingdom': 'GB', Australia: 'AU', Argentina: 'AR',
  Brazil: 'BR', Canada: 'CA', Japan: 'JP', China: 'CN', 'Czech Republic': 'CZ',
  Poland: 'PL', Croatia: 'HR', Greece: 'GR', Norway: 'NO', Denmark: 'DK',
  Netherlands: 'NL', Belgium: 'BE', Austria: 'AT', Bulgaria: 'BG', Romania: 'RO',
  Hungary: 'HU', Ukraine: 'UA', Kazakhstan: 'KZ', Georgia: 'GE', Chile: 'CL',
  Colombia: 'CO', Peru: 'PE', Uruguay: 'UY', Mexico: 'MX', 'South Korea': 'KR',
  Korea: 'KR', Taiwan: 'TW', 'Chinese Taipei': 'TW', Thailand: 'TH', India: 'IN',
  Portugal: 'PT', Sweden: 'SE', Finland: 'FI', Slovakia: 'SK', Slovenia: 'SI',
  Estonia: 'EE', Latvia: 'LV', Lithuania: 'LT', Belarus: 'BY', Israel: 'IL',
  Tunisia: 'TN', 'South Africa': 'ZA', Egypt: 'EG', Morocco: 'MA',
  'New Zealand': 'NZ', Liechtenstein: 'LI', Luxembourg: 'LU', Monaco: 'MC',
  Ireland: 'IE', Iceland: 'IS', Cyprus: 'CY', Turkey: 'TR',
  'Bosnia and Herzegovina': 'BA', Montenegro: 'ME', 'North Macedonia': 'MK',
  Albania: 'AL', Moldova: 'MD', Armenia: 'AM', Azerbaijan: 'AZ',
  Uzbekistan: 'UZ', Philippines: 'PH', Indonesia: 'ID', Vietnam: 'VN',
  Malaysia: 'MY', Singapore: 'SG', 'Hong Kong': 'HK', Pakistan: 'PK',
  Bangladesh: 'BD', 'Sri Lanka': 'LK', Nigeria: 'NG', Kenya: 'KE',
  Ecuador: 'EC', Bolivia: 'BO', Paraguay: 'PY', Venezuela: 'VE',
  'Dominican Republic': 'DO', 'Puerto Rico': 'PR', Jamaica: 'JM',
  Bahamas: 'BS', 'Costa Rica': 'CR', Panama: 'PA', Guatemala: 'GT',
  'El Salvador': 'SV', Honduras: 'HN', Nicaragua: 'NI', Cuba: 'CU',
  Qatar: 'QA', 'United Arab Emirates': 'AE', 'Saudi Arabia': 'SA', Kuwait: 'KW',
}

export function countryFlag(countryName: string | null | undefined): string {
  if (!countryName) return ''
  const iso2 = COUNTRY_TO_ISO2[countryName.trim()]
  if (!iso2) return ''
  const codePoints = [...iso2.toUpperCase()].map((c) => 0x1f1e6 - 65 + c.charCodeAt(0))
  return String.fromCodePoint(...codePoints)
}
