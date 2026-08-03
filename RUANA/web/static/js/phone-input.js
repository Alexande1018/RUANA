/**
 * Selector de teléfono internacional para formularios RUANA.
 */
(function (global) {
    function digitsOnly(value) {
        return String(value || '').replace(/\D/g, '');
    }

    class RuanaPhoneInput {
        constructor(options) {
            this.root = options.root;
            this.hiddenInput = options.hiddenInput;
            this.nationalInput = options.nationalInput;
            this.trigger = options.trigger;
            this.dropdown = options.dropdown;
            this.searchInput = options.searchInput;
            this.listEl = options.listEl;
            this.flagEl = options.flagEl;
            this.dialEl = options.dialEl;
            this.countries = global.RUANA_PHONE_COUNTRIES || [];
            this.selectedIso = options.defaultIso || 'ES';
            this.selectedCountry = this.findCountry(this.selectedIso) || this.countries[0];
            this._boundClose = this.closeDropdown.bind(this);
            this.init();
        }

        findCountry(iso) {
            return this.countries.find(function (country) {
                return country.iso === iso;
            }) || null;
        }

        init() {
            this.renderCountryList();
            this.selectCountry(this.selectedCountry.iso, false);
            this.bindEvents();
            this.syncHiddenInput();
        }

        bindEvents() {
            var self = this;
            this.trigger.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (self.dropdown.hidden) self.openDropdown();
                else self.closeDropdown();
            });

            this.searchInput.addEventListener('input', function () {
                self.filterCountries(self.searchInput.value);
            });

            this.nationalInput.addEventListener('input', function () {
                self.syncHiddenInput();
            });

            document.addEventListener('click', this._boundClose);
            document.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') self.closeDropdown();
            });
        }

        openDropdown() {
            this.dropdown.hidden = false;
            this.trigger.setAttribute('aria-expanded', 'true');
            this.searchInput.value = '';
            this.filterCountries('');
            this.searchInput.focus();
        }

        closeDropdown(event) {
            if (event && this.root.contains(event.target)) {
                if (event.target === this.trigger || this.trigger.contains(event.target)) return;
                if (this.dropdown.contains(event.target)) return;
            }
            this.dropdown.hidden = true;
            this.trigger.setAttribute('aria-expanded', 'false');
        }

        renderCountryList(filtered) {
            var self = this;
            var list = filtered || this.countries;
            this.listEl.innerHTML = '';
            list.forEach(function (country) {
                var item = document.createElement('li');
                item.className = 'phone-country-item';
                item.setAttribute('role', 'option');
                item.setAttribute('data-iso', country.iso);
                item.innerHTML =
                    '<span class="phone-country-item-flag">' + global.ruanaCountryFlag(country.iso) + '</span>' +
                    '<span class="phone-country-item-name">' + country.name + '</span>' +
                    '<span class="phone-country-item-dial">+' + country.dial + '</span>';
                item.addEventListener('click', function () {
                    self.selectCountry(country.iso);
                    self.closeDropdown();
                    self.nationalInput.focus();
                });
                self.listEl.appendChild(item);
            });
        }

        filterCountries(query) {
            var normalized = String(query || '').trim().toLowerCase();
            if (!normalized) {
                this.renderCountryList(this.countries);
                return;
            }
            var filtered = this.countries.filter(function (country) {
                return country.name.toLowerCase().indexOf(normalized) !== -1
                    || country.iso.toLowerCase().indexOf(normalized) !== -1
                    || ('+' + country.dial).indexOf(normalized.replace(/\s/g, '')) !== -1
                    || country.dial.indexOf(normalized.replace(/\D/g, '')) === 0;
            });
            this.renderCountryList(filtered);
        }

        selectCountry(iso, sync) {
            if (sync === undefined) sync = true;
            var country = this.findCountry(iso);
            if (!country) return;
            this.selectedIso = country.iso;
            this.selectedCountry = country;
            this.flagEl.textContent = global.ruanaCountryFlag(country.iso);
            this.dialEl.textContent = '+' + country.dial;
            this.trigger.setAttribute('aria-label', 'País seleccionado: ' + country.name);
            if (sync) this.syncHiddenInput();
        }

        getNationalDigits() {
            return digitsOnly(this.nationalInput.value);
        }

        getFullNumber() {
            var national = this.getNationalDigits();
            if (!national) return '';
            return '+' + this.selectedCountry.dial + national;
        }

        syncHiddenInput() {
            if (this.hiddenInput) this.hiddenInput.value = this.getFullNumber();
        }

        isValid() {
            var digits = digitsOnly(this.getFullNumber());
            return digits.length >= 7;
        }
    }

    global.RuanaPhoneInput = RuanaPhoneInput;
})(window);
