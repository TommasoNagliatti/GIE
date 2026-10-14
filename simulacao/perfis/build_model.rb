# Independent 2025 buildings; EnergyPlus thermal simulation, explicit appliance schedules.
require 'openstudio'
require 'json'
root=File.dirname(File.expand_path(__FILE__))
profile=ARGV.fetch(0); dir=File.join(root,profile)
Dir.chdir(dir)
cfg=JSON.parse(File.read(File.join(dir,'parameters.json')))
house=cfg['n_evse']==1
m=OpenStudio::Model::Model.new
m.getTimestep.setNumberOfTimestepsPerHour(4)
m.getYearDescription.setCalendarYear(2025)
rp=m.getRunPeriod;rp.setBeginMonth(1);rp.setBeginDayOfMonth(1);rp.setEndMonth(12);rp.setEndDayOfMonth(31)
rp.setUseWeatherFileHolidays(false);rp.setUseWeatherFileDaylightSavings(false)
sc=m.getSimulationControl;sc.setDoZoneSizingCalculation(true);sc.setDoSystemSizingCalculation(false);sc.setDoPlantSizingCalculation(false)
sc.setRunSimulationforSizingPeriods(false);sc.setRunSimulationforWeatherFileRunPeriods(true)
epw=OpenStudio::EpwFile.new(OpenStudio::Path.new(Dir[File.join(root,'weather','*.epw')].first))
OpenStudio::Model::WeatherFile.setWeatherFile(m,epw)
site=m.getSite;site.setLatitude(epw.latitude);site.setLongitude(epw.longitude);site.setTimeZone(epw.timeZone);site.setElevation(epw.elevation)
ddy=OpenStudio::EnergyPlus.loadAndTranslateIdf(OpenStudio::Path.new(Dir[File.join(root,'weather','*.ddy')].first)).get
ddy.getDesignDays.select{|d|d.nameString.include?('Ann Htg 99.6%')||d.nameString.include?('Ann Clg .4% Condns DB=>MWB')}.each{|d|d.clone(m)}

def construction(m,name,layers)
 c=OpenStudio::Model::Construction.new(m);c.setName(name)
 layers.each_with_index do |p,i|
  mat=OpenStudio::Model::StandardOpaqueMaterial.new(m);mat.setName("#{name}_#{i}")
  mat.setThickness(p[0]);mat.setConductivity(p[1]);mat.setDensity(p[2]);mat.setSpecificHeat(p[3]);c.insertLayer(i,mat)
 end
 c
end
wall=construction(m,'Rendered masonry',[[0.02,1,1800,840],[0.14,0.6,1200,840],[0.02,1,1800,840]])
roof=construction(m,'Insulated roof',[[0.02,0.8,1800,840],[0.04,0.04,30,1400],[0.02,0.16,800,1090]])
slab=construction(m,'Concrete slab',[[0.15,1.7,2300,880]])
glass=OpenStudio::Model::SimpleGlazing.new(m);glass.setUFactor(3.0);glass.setSolarHeatGainCoefficient(0.4);glass.setVisibleTransmittance(0.6)
win=OpenStudio::Model::Construction.new(m);win.insertLayer(0,glass)
external=OpenStudio::Model::ExternalFile.getExternalFile(m,File.join(dir,'schedules.csv'),false).get
columns=cfg['loads'].keys+['hvac_available','people_fraction']
schedules={}
columns.each_with_index do |name,i|
 s=OpenStudio::Model::ScheduleFile.new(external,i+1,1);s.setName(name)
 s.setNumberofHoursofData(8760);s.setMinutesperItem(15);s.setInterpolatetoTimestep(false)
 schedules[name]=s
end
activity=OpenStudio::Model::ScheduleConstant.new(m);activity.setValue(110)
spaces=OpenStudio::Model::SpaceVector.new
geometry=house ? [[0,0,6,10,'Living',false],[6,0,2,10,'Bedroom',true]] : [[0,0,15,10,'Convenience',true]]
geometry.each do |x,y,w,l,name,conditioned|
 pts=OpenStudio::Point3dVector.new
 [[x,y,0],[x,y+l,0],[x+w,y+l,0],[x+w,y,0]].each{|a|pts<<OpenStudio::Point3d.new(*a)}
 s=OpenStudio::Model::Space.fromFloorPrint(pts,3.0,m).get;s.setName(name);spaces<<s
 zone=OpenStudio::Model::ThermalZone.new(m);zone.setName(name);s.setThermalZone(zone)
 inf=OpenStudio::Model::SpaceInfiltrationDesignFlowRate.new(m);inf.setSpace(s);inf.setAirChangesperHour(house ? 0.5 : 0.6);inf.setSchedule(m.alwaysOnDiscreteSchedule)
 pd=OpenStudio::Model::PeopleDefinition.new(m);pd.setNumberofPeople(house ? (conditioned ? 1 : 2) : 10)
 people=OpenStudio::Model::People.new(pd);people.setSpace(s);people.setNumberofPeopleSchedule(schedules['people_fraction']);people.setActivityLevelSchedule(activity)
 cfg['loads'].each do |key,load|
  # Distribute residential lights/standby, keep wet and kitchen loads in living zone.
  share=house ? ((['lights','standby','fan'].include?(key)) ? (conditioned ? 0.25 : 0.75) : (conditioned ? 0 : 1)) : 1
  next if share==0
  ed=OpenStudio::Model::ElectricEquipmentDefinition.new(m);ed.setDesignLevel(load['kw']*1000*share);ed.setFractionLost(load['lost']);ed.setFractionRadiant(0.1*(1-load['lost']))
  e=OpenStudio::Model::ElectricEquipment.new(ed);e.setName("#{key}_#{name}");e.setSpace(s);e.setSchedule(schedules[key]);e.setEndUseSubcategory(key)
 end
 next unless conditioned
 cool=OpenStudio::Model::ScheduleConstant.new(m);cool.setValue(24)
 heat=OpenStudio::Model::ScheduleConstant.new(m);heat.setValue(5)
 thermostat=OpenStudio::Model::ThermostatSetpointDualSetpoint.new(m);thermostat.setCoolingSetpointTemperatureSchedule(cool);thermostat.setHeatingSetpointTemperatureSchedule(heat);zone.setThermostatSetpointDualSetpoint(thermostat)
 fan=OpenStudio::Model::FanOnOff.new(m);fan.setPressureRise(60);fan.setFanEfficiency(0.6);fan.setMaximumFlowRate(house ? 0.14 : 0.8)
 heating=OpenStudio::Model::CoilHeatingElectric.new(m);heating.setNominalCapacity(0)
 cooling=OpenStudio::Model::CoilCoolingDXSingleSpeed.new(m);cooling.setRatedCOP(3.2);cooling.setRatedTotalCoolingCapacity(house ? 2500 : 16000);cooling.setRatedAirFlowRate(house ? 0.14 : 0.8)
 unit=OpenStudio::Model::ZoneHVACPackagedTerminalAirConditioner.new(m,schedules['hvac_available'],fan,heating,cooling)
 unit.setSupplyAirFlowRateDuringCoolingOperation(house ? 0.14 : 0.8);unit.setSupplyAirFlowRateDuringHeatingOperation(house ? 0.14 : 0.8);unit.setSupplyAirFlowRateWhenNoCoolingorHeatingisNeeded(0)
 unit.setOutdoorAirFlowRateDuringCoolingOperation(0);unit.setOutdoorAirFlowRateDuringHeatingOperation(0);unit.setOutdoorAirFlowRateWhenNoCoolingorHeatingisNeeded(0)
 unit.addToThermalZone(zone)
end
OpenStudio::Model.matchSurfaces(spaces)
m.getSurfaces.each do |s|
 s.setConstruction(s.surfaceType=='Wall' ? wall : (s.surfaceType=='RoofCeiling' && s.outsideBoundaryCondition=='Outdoors' ? roof : slab))
 if s.surfaceType=='Wall' && s.outsideBoundaryCondition=='Outdoors'
  w=s.setWindowToWallRatio(house ? 0.15 : 0.25);w.get.setConstruction(win) if w.is_initialized
 end
end
ground=m.getSiteGroundTemperatureBuildingSurface
%w[January February March April May June July August September October November December].zip([23,24,24,22,20,18,17,18,19,20,21,22]).each{|month,t|ground.send("set#{month}GroundTemperature",t)}
['Electricity:Facility','Cooling:Electricity','Heating:Electricity','Fans:Electricity','InteriorEquipment:Electricity'].each{|n|o=OpenStudio::Model::OutputMeter.new(m);o.setName(n);o.setReportingFrequency('Timestep')}
['Site Outdoor Air Drybulb Temperature','Site Outdoor Air Relative Humidity','Zone Mean Air Temperature'].each{|n|o=OpenStudio::Model::OutputVariable.new(n,m);o.setReportingFrequency('Timestep')}
m.getOutputControlFiles.setOutputCSV(true)
raise 'Area mismatch' unless (m.getBuilding.floorArea-cfg['area']).abs<0.01
m.save(OpenStudio::Path.new(File.join(dir,'building.osm')),true)
ft=OpenStudio::EnergyPlus::ForwardTranslator.new;idf=ft.translateModel(m)
raise ft.errors.map(&:logMessage).join("\n") unless ft.errors.empty?
idf.objects.select{|o|o.iddObject.name.start_with?('LifeCycleCost:')}.each(&:remove)
idf.save(OpenStudio::Path.new(File.join(dir,'building.idf')),true)
puts JSON.generate({profile:profile,area_m2:m.getBuilding.floorArea,zones:m.getThermalZones.size,warnings:ft.warnings.map(&:logMessage)})


