Name:           zyntrix-compatibility-fabric
Version:        0.1.0
Release:        1%{?dist}
Summary:        Universal Application Compatibility Fabric and Runtime Orchestrator

License:        Apache-2.0
URL:            https://github.com/zyntrix-labs/zcf
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
Requires:       python3 >= 3.10
Recommends:     wine
Recommends:     qemu-user-static

%description
ZCF coordinates compatibility runtimes (Wine, Proton, QEMU, Box64),
diagnoses execution failures, and shares compatibility profiles
across Linux distributions.

%prep
%autosetup

%build
%py3_build

%install
%py3_install

%files
%license LICENSE
%doc README.md
%{_bindir}/zcf
%{python3_sitelib}/zcf/
%{python3_sitelib}/zyntrix_compatibility_fabric-*.egg-info/

%changelog
* Sat Oct 24 2026 Zyntrix Labs Engineering <engineering@zyntrixlabs.org> - 0.1.0-1
- Initial packaging for Fedora and RHEL.
