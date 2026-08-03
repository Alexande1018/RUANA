/**
 * Catálogo de países para el selector telefónico de RUANA.
 * dial: indicativo sin el signo +.
 */
(function (global) {
    const PRIORITY_ISOS = ['ES', 'CO', 'MX', 'AR', 'PE', 'CL', 'EC', 'VE', 'US', 'GB', 'FR', 'DE', 'IT', 'PT'];

    const COUNTRIES = [
        { iso: 'ES', name: 'España', dial: '34' },
        { iso: 'CO', name: 'Colombia', dial: '57' },
        { iso: 'MX', name: 'México', dial: '52' },
        { iso: 'AR', name: 'Argentina', dial: '54' },
        { iso: 'PE', name: 'Perú', dial: '51' },
        { iso: 'CL', name: 'Chile', dial: '56' },
        { iso: 'EC', name: 'Ecuador', dial: '593' },
        { iso: 'VE', name: 'Venezuela', dial: '58' },
        { iso: 'US', name: 'Estados Unidos', dial: '1' },
        { iso: 'GB', name: 'Reino Unido', dial: '44' },
        { iso: 'FR', name: 'Francia', dial: '33' },
        { iso: 'DE', name: 'Alemania', dial: '49' },
        { iso: 'IT', name: 'Italia', dial: '39' },
        { iso: 'PT', name: 'Portugal', dial: '351' },
        { iso: 'AD', name: 'Andorra', dial: '376' },
        { iso: 'AE', name: 'Emiratos Árabes Unidos', dial: '971' },
        { iso: 'AU', name: 'Australia', dial: '61' },
        { iso: 'BE', name: 'Bélgica', dial: '32' },
        { iso: 'BO', name: 'Bolivia', dial: '591' },
        { iso: 'BR', name: 'Brasil', dial: '55' },
        { iso: 'CA', name: 'Canadá', dial: '1' },
        { iso: 'CH', name: 'Suiza', dial: '41' },
        { iso: 'CR', name: 'Costa Rica', dial: '506' },
        { iso: 'CU', name: 'Cuba', dial: '53' },
        { iso: 'DO', name: 'República Dominicana', dial: '1' },
        { iso: 'DZ', name: 'Argelia', dial: '213' },
        { iso: 'GT', name: 'Guatemala', dial: '502' },
        { iso: 'HN', name: 'Honduras', dial: '504' },
        { iso: 'IE', name: 'Irlanda', dial: '353' },
        { iso: 'IN', name: 'India', dial: '91' },
        { iso: 'JP', name: 'Japón', dial: '81' },
        { iso: 'MA', name: 'Marruecos', dial: '212' },
        { iso: 'NI', name: 'Nicaragua', dial: '505' },
        { iso: 'NL', name: 'Países Bajos', dial: '31' },
        { iso: 'NO', name: 'Noruega', dial: '47' },
        { iso: 'NZ', name: 'Nueva Zelanda', dial: '64' },
        { iso: 'PA', name: 'Panamá', dial: '507' },
        { iso: 'PL', name: 'Polonia', dial: '48' },
        { iso: 'PY', name: 'Paraguay', dial: '595' },
        { iso: 'RO', name: 'Rumanía', dial: '40' },
        { iso: 'RU', name: 'Rusia', dial: '7' },
        { iso: 'SE', name: 'Suecia', dial: '46' },
        { iso: 'SV', name: 'El Salvador', dial: '503' },
        { iso: 'TR', name: 'Turquía', dial: '90' },
        { iso: 'UA', name: 'Ucrania', dial: '380' },
        { iso: 'UY', name: 'Uruguay', dial: '598' },
    ];

    function countryFlag(iso) {
        if (!iso || iso.length !== 2) return '🌐';
        const code = iso.toUpperCase();
        return String.fromCodePoint(
            ...[...code].map(function (char) {
                return 0x1f1e6 - 65 + char.charCodeAt(0);
            })
        );
    }

    function sortCountries(list) {
        const priority = new Map(PRIORITY_ISOS.map(function (iso, index) { return [iso, index]; }));
        return list.slice().sort(function (a, b) {
            const pa = priority.has(a.iso) ? priority.get(a.iso) : 999;
            const pb = priority.has(b.iso) ? priority.get(b.iso) : 999;
            if (pa !== pb) return pa - pb;
            return a.name.localeCompare(b.name, 'es');
        });
    }

    global.RUANA_PHONE_COUNTRIES = sortCountries(COUNTRIES);
    global.ruanaCountryFlag = countryFlag;
})(window);
