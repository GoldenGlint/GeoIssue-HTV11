/** Replace these seed records or implement issueRepository.list() with your API.
 * Coordinates are already coarsened for this public prototype. All records are fictional.
 * Backend authorization/privacy processing must happen before returning real records.
 */
export const DEMO_DATE = '2026-10-17T12:00:00Z';
export const categories = {
  Pothole: { color: '#fa6575', icon: 'warning' },
  'Sidewalk damage': { color: '#ffb452', icon: 'cone' },
  Graffiti: { color: '#ba80f6', icon: 'tool' },
  Litter: { color: '#25d5ac', icon: 'trash' },
  Flooding: { color: '#4ea8ff', icon: 'water' },
  Other: { color: '#9daec3', icon: 'more' },
};
const seed = [
  ['Pothole','High','Open','Downtown','King St W & Spadina Ave',-79.395,43.646,'TTC','Spadina streetcar stop',180,3,96,35],
  ['Sidewalk damage','Medium','In review','Kensington Market','Augusta Ave & Baldwin St',-79.402,43.655,'Schools','Kensington Community School',240,2,89,65],
  ['Graffiti','Low','Resolved','East York','Coxwell Ave & Danforth Ave',-79.322,43.684,'TTC','Coxwell Station',120,4,84,90],
  ['Litter','Low','Open','The Junction','Dundas St W & Keele St',-79.467,43.665,'Roads','Dundas Street West',45,2,93,40],
  ['Flooding','High','In review','Riverside','Queen St E & Broadview Ave',-79.353,43.659,'TTC','Queen streetcar stop',90,5,91,120],
  ['Pothole','High','Open','Parkdale','Queen St W & Dufferin St',-79.428,43.642,'Roads','Queen Street West',30,3,94,50],
  ['Sidewalk damage','Medium','Resolved','North York','Yonge St & Sheppard Ave',-79.411,43.761,'TTC','Sheppard–Yonge Station',220,1,86,80],
  ['Graffiti','Low','Open','Scarborough','Eglinton Ave E & Kennedy Rd',-79.263,43.733,'TTC','Kennedy Station',380,2,82,140],
  ['Litter','Low','Open','Downtown','Bay St & Front St W',-79.379,43.646,'TTC','Union Station',160,6,97,30],
  ['Flooding','High','In review','Etobicoke','The Queensway & Islington Ave',-79.519,43.625,'Roads','The Queensway',65,3,90,100],
  ['Pothole','Medium','Open','East York',"O’Connor Dr & Donlands Ave",-79.349,43.697,'Schools','William Burgess Elementary',420,1,88,75],
  ['Sidewalk damage','Medium','Open','Leslieville','Queen St E & Leslie St',-79.329,43.663,'Schools','Leslieville Junior Public',280,2,85,110],
  ['Pothole','High','In review','Downtown','Adelaide St W & Peter St',-79.392,43.648,'Roads','Adelaide Street West',20,4,95,45],
  ['Litter','Medium','Open','Kensington Market','Spadina Ave & College St',-79.400,43.658,'TTC','Spadina streetcar stop',310,3,92,60],
  ['Graffiti','Low','Resolved','The Annex','Bloor St W & Bathurst St',-79.411,43.666,'TTC','Bathurst Station',140,2,81,95],
  ['Sidewalk damage','Medium','Open','High Park','Bloor St W & Parkside Dr',-79.458,43.655,'TTC','Keele Station',200,1,87,70],
  ['Flooding','High','Open','Liberty Village','East Liberty St & Strachan Ave',-79.411,43.639,'Roads','Strachan Avenue',80,4,94,90],
  ['Other','Low','In review','The Beaches','Queen St E & Woodbine Ave',-79.306,43.668,'Roads','Queen Street East',60,1,78,180],
  ['Litter','Low','Resolved','Downtown','University Ave & Dundas St W',-79.388,43.655,'TTC','St Patrick Station',100,2,95,40],
  ['Pothole','Medium','Open','The Annex','Bloor St W & St George St',-79.400,43.668,'TTC','St George Station',120,3,92,55],
  ['Graffiti','Low','Open','Riverside','Dundas St E & Broadview Ave',-79.354,43.664,'Schools','Queen Alexandra Middle School',330,2,88,75],
  ['Sidewalk damage','High','In review','Downtown','Queen St W & University Ave',-79.386,43.650,'TTC','Osgoode Station',75,3,96,45],
  ['Other','Medium','Open','Scarborough','Military Trail & Ellesmere Rd',-79.188,43.785,'Schools','University of Toronto Scarborough',150,1,80,160],
  ['Litter','Low','Open','Leslieville','Dundas St E & Carlaw Ave',-79.341,43.666,'Roads','Carlaw Avenue',25,2,91,65],
];
export const demoIssues = seed.map((s, i) => ({
  issue_id: `CL-${10472-i}`, incident_id: `INC-${2000+i}`,
  issue_type:s[0], severity:s[1], resolution_status:s[2], neighbourhood_id:s[3], address:s[4],
  geometry:{type:'Point',coordinates:[s[5],s[6]]}, infrastructure_type:s[7], asset_name:s[8], distance_m:s[9],
  sightings_count:s[10], detection_confidence:s[11]/100, location_radius_m:s[12], geo_confidence:0.82,
  verification_status:i%4===0?'Needs review':'Verified',
  first_seen_at:new Date(Date.parse(DEMO_DATE)-(i%24)*86400000-7200000).toISOString(),
  last_seen_at:new Date(Date.parse(DEMO_DATE)-(i%5)*86400000).toISOString(),
  source_category:i%3===0?'Community submission':'Public imagery', evidence_thumbnail:null,
  description: `${s[0]} observed near ${s[4]}. This is an illustrative record for the CivicLens prototype.`,
  explanation:`The sample image analysis indicates ${s[0].toLowerCase()}. Location is approximate within ${s[12]} metres. A reviewer should confirm the issue and location before any operational action.`,
  ward_id:s[3]==='Scarborough'?'25':'10', is_demo:true,
}));

export const issueRepository = {
  async list() { return structuredClone(demoIssues); },
  async submit(draft) {
    // Replace with POST /api/submissions. Do not publish uploads until privacy review.
    return { ...draft, issue_id:`LOCAL-${Date.now().toString(36).toUpperCase()}`, verification_status:'Pending review', local_only:true };
  },
};
